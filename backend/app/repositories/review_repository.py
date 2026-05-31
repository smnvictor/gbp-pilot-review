from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from app.models.enums import ReviewStatus
from app.models.review import Review
from app.repositories.base import CRUDRepository


class ReviewRepository(CRUDRepository[Review]):
    model = Review

    async def get_by_google_id(self, google_review_id: str) -> Review | None:
        stmt = select(Review).where(Review.google_review_id == google_review_id)
        return (await self.session.scalars(stmt)).first()

    async def list_by_status(self, status: ReviewStatus, limit: int = 100) -> Sequence[Review]:
        stmt = (
            select(Review)
            .where(Review.status == status)
            .order_by(Review.created_at.desc())
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()

    async def list_for_location(self, location_id: UUID, limit: int = 100) -> Sequence[Review]:
        stmt = (
            select(Review)
            .where(Review.location_id == location_id)
            .order_by(Review.posted_at.desc())
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()
