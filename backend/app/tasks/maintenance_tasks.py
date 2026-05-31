import asyncio
from datetime import UTC, datetime, timedelta

from loguru import logger

from app.celery_app import celery_app


@celery_app.task(name="app.tasks.maintenance_tasks.check_quota_thresholds")  # type: ignore[untyped-decorator]
def check_quota_thresholds() -> int:
    """Daily 09:00 UTC: alert clients at 80% / 100% quota usage."""
    from sqlalchemy import select

    from app.database import get_sessionmaker
    from app.models.client import Client
    from app.models.subscription import Subscription
    from app.repositories.quota_repository import QuotaRepository, current_year_month
    from app.services.notification_service import NotificationService

    async def _run() -> int:
        sm = get_sessionmaker()
        notified = 0
        async with sm() as session:
            stmt = select(Client.id, Subscription.monthly_response_quota).join(
                Subscription, Subscription.client_id == Client.id
            )
            rows = (await session.execute(stmt)).all()
            quotas = QuotaRepository(session)
            ym = current_year_month()
            for client_id, monthly in rows:
                usage = await quotas.get_or_create(client_id, ym)
                if monthly <= 0:
                    continue
                pct = usage.count * 100 // monthly
                threshold: int | None = None
                if pct >= 100 and (usage.last_alert_threshold or 0) < 100:
                    threshold = 100
                    event = "quota_exhausted"
                elif pct >= 80 and (usage.last_alert_threshold or 0) < 80:
                    threshold = 80
                    event = "quota_warning_80"
                else:
                    continue
                await NotificationService(session).dispatch(
                    event_type=event,
                    client_id=client_id,
                    payload={"used": usage.count, "quota": monthly},
                )
                usage.last_alert_threshold = threshold
                notified += 1
            await session.commit()
        return notified

    return asyncio.run(_run())


@celery_app.task(name="app.tasks.maintenance_tasks.purge_expired_data")  # type: ignore[untyped-decorator]
def purge_expired_data() -> int:
    """Daily 03:15 UTC: hard-delete soft-deleted users/clients older than 30d (RGPD)."""
    from sqlalchemy import delete

    from app.database import get_sessionmaker
    from app.models.client import Client
    from app.models.user import User

    async def _run() -> int:
        sm = get_sessionmaker()
        cutoff = datetime.now(UTC) - timedelta(days=30)
        async with sm() as session:
            users_deleted = await session.execute(
                delete(User).where(User.deleted_at.is_not(None), User.deleted_at < cutoff)
            )
            clients_deleted = await session.execute(
                delete(Client).where(Client.deleted_at.is_not(None), Client.deleted_at < cutoff)
            )
            await session.commit()
            total = (getattr(users_deleted, "rowcount", 0) or 0) + (
                getattr(clients_deleted, "rowcount", 0) or 0
            )
            logger.info("Purge RGPD: {n} rows hard-deleted", n=total)
            return total

    return asyncio.run(_run())
