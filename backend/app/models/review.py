from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, TIMESTAMP, CheckConstraint, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, uuid7
from app.models.enums import ReviewStatus


class Review(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating_range"),)

    id: Mapped[UUID] = mapped_column(default=uuid7, primary_key=True)
    location_id: Mapped[UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    google_review_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    reviewer_display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewer_first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(CHAR(2), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_edited_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    parent_review_id: Mapped[UUID | None] = mapped_column(ForeignKey("reviews.id"), nullable=True)
    status: Mapped[ReviewStatus] = mapped_column(
        ENUM(ReviewStatus, name="review_status", create_type=True),
        nullable=False,
        default=ReviewStatus.detected,
    )
    block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
