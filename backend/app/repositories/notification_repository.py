from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from app.models.enums import NotificationStatus
from app.models.notification import Notification
from app.models.notification_preference import NotificationPreference
from app.repositories.base import CRUDRepository


class NotificationPreferenceRepository(CRUDRepository[NotificationPreference]):
    model = NotificationPreference

    async def get_by_client(self, client_id: UUID) -> NotificationPreference | None:
        stmt = select(NotificationPreference).where(NotificationPreference.client_id == client_id)
        return (await self.session.scalars(stmt)).first()


class NotificationRepository(CRUDRepository[Notification]):
    model = Notification

    async def list_pending_digests(
        self, client_id: UUID, limit: int = 200
    ) -> Sequence[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.client_id == client_id,
                Notification.status == NotificationStatus.deferred,
            )
            .order_by(Notification.created_at)
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()
