from datetime import time
from uuid import UUID

from sqlalchemy import CHAR, Boolean, CheckConstraint, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import ARRAY, ENUM
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Time

from app.models.base import Base, TimestampMixin, uuid7
from app.models.enums import NoTextReviewPolicy, PublishDelayRange, ValidationMode


class ClientSettings(Base, TimestampMixin):
    __tablename__ = "client_settings"
    __table_args__ = (
        CheckConstraint(
            "publish_window_end > publish_window_start", name="ck_publish_window_order"
        ),
    )

    id: Mapped[UUID] = mapped_column(default=uuid7, primary_key=True)
    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    polling_frequency_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1440)
    publish_delay_range: Mapped[PublishDelayRange] = mapped_column(
        ENUM(
            PublishDelayRange,
            name="publish_delay_range",
            create_type=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PublishDelayRange.range_1d_2d,
    )
    publish_window_start: Mapped[time] = mapped_column(Time, nullable=False, default=time(9, 0))
    publish_window_end: Mapped[time] = mapped_column(Time, nullable=False, default=time(21, 0))
    publish_window_timezone: Mapped[str] = mapped_column(
        String, nullable=False, default="Europe/Paris"
    )
    language_override: Mapped[str | None] = mapped_column(CHAR(2), nullable=True)
    no_text_review_policy: Mapped[NoTextReviewPolicy] = mapped_column(
        ENUM(NoTextReviewPolicy, name="no_text_review_policy", create_type=True),
        nullable=False,
        default=NoTextReviewPolicy.reply_4_5_only,
    )
    validation_mode: Mapped[ValidationMode] = mapped_column(
        ENUM(ValidationMode, name="validation_mode", create_type=True),
        nullable=False,
        default=ValidationMode.suggestion,
    )
    digest_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    digest_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=9)
    regex_blocklist: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
