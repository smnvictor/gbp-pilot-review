from datetime import datetime
from uuid import UUID

from sqlalchemy import TIMESTAMP, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, uuid7
from app.models.enums import ClientStatus


class Client(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "clients"

    id: Mapped[UUID] = mapped_column(default=uuid7, primary_key=True)
    business_name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    business_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tone_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tone: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    always_mention: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    never_mention: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[ClientStatus] = mapped_column(
        ENUM(ClientStatus, name="client_status", create_type=True),
        nullable=False,
        default=ClientStatus.active,
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
