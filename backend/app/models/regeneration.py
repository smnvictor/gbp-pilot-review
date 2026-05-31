from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, uuid7


class Regeneration(Base, CreatedAtMixin):
    __tablename__ = "regenerations"

    id: Mapped[UUID] = mapped_column(default=uuid7, primary_key=True)
    review_id: Mapped[UUID] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
