from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update

from app.models.quota_usage import QuotaUsage
from app.repositories.base import CRUDRepository


def current_year_month() -> str:
    now = datetime.now(UTC)
    return f"{now.year:04d}-{now.month:02d}"


class QuotaRepository(CRUDRepository[QuotaUsage]):
    model = QuotaUsage

    async def get_or_create(self, client_id: UUID, year_month: str | None = None) -> QuotaUsage:
        ym = year_month or current_year_month()
        stmt = select(QuotaUsage).where(
            QuotaUsage.client_id == client_id, QuotaUsage.year_month == ym
        )
        existing = (await self.session.scalars(stmt)).first()
        if existing is not None:
            return existing
        usage = QuotaUsage(client_id=client_id, year_month=ym, count=0)
        await self.add(usage)
        return usage

    async def increment(self, client_id: UUID) -> int:
        ym = current_year_month()
        usage = await self.get_or_create(client_id, ym)
        await self.session.execute(
            update(QuotaUsage).where(QuotaUsage.id == usage.id).values(count=QuotaUsage.count + 1)
        )
        await self.session.flush()
        await self.session.refresh(usage)
        return usage.count
