import asyncio
from typing import Any
from uuid import UUID

from app.celery_app import celery_app


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.tasks.notification_tasks.send_notification",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_notification(  # type: ignore[no-untyped-def]
    self, event_type: str, client_id: str, payload: dict[str, Any]
) -> str:
    from app.database import get_sessionmaker
    from app.services.notification_service import NotificationService

    async def _run() -> str:
        sm = get_sessionmaker()
        async with sm() as session:
            service = NotificationService(session)
            notif = await service.dispatch(
                event_type=event_type, client_id=UUID(client_id), payload=payload
            )
            return notif.status.value

    return asyncio.run(_run())


@celery_app.task(name="app.tasks.notification_tasks.send_pending_digests")  # type: ignore[untyped-decorator]
def send_pending_digests() -> int:
    """Beat job: aggregate deferred notifications per client and send digest."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.database import get_sessionmaker
    from app.models.client_settings import ClientSettings
    from app.models.enums import NotificationStatus
    from app.models.notification import Notification
    from app.repositories.notification_repository import (
        NotificationPreferenceRepository,
    )
    from app.services.notification_templates import render

    async def _run() -> int:
        sm = get_sessionmaker()
        sent = 0
        async with sm() as session:
            cs_stmt = select(ClientSettings).where(ClientSettings.digest_mode.is_(True))
            client_settings = (await session.scalars(cs_stmt)).all()
            for cs in client_settings:
                stmt = (
                    select(Notification)
                    .where(
                        Notification.client_id == cs.client_id,
                        Notification.status == NotificationStatus.deferred,
                    )
                    .order_by(Notification.created_at)
                )
                pendings = (await session.scalars(stmt)).all()
                if not pendings:
                    continue
                pref = await NotificationPreferenceRepository(session).get_by_client(cs.client_id)
                if pref is None or pref.email_address is None:
                    continue
                lines = []
                for n in pendings:
                    _, _, text = render(n.event_type, n.payload or {})
                    lines.append(f"- {text}")
                body_text = "Récapitulatif des événements:\n\n" + "\n".join(lines)
                body_html = (
                    "<p>Récapitulatif des événements :</p><ul>"
                    + "".join(f"<li>{line[2:]}</li>" for line in lines)
                    + "</ul>"
                )
                from app.integrations.resend.client import ResendClient, ResendError

                try:
                    await ResendClient().send_email(
                        to=pref.email_address,
                        subject="Digest GBP Pilot Review",
                        html=body_html,
                        text=body_text,
                    )
                except ResendError:
                    continue
                now = datetime.now(UTC)
                for n in pendings:
                    n.status = NotificationStatus.sent
                    n.sent_at = now
                    sent += 1
            await session.commit()
        return sent

    return asyncio.run(_run())
