from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DeadLetterJob(Base):
    __tablename__ = "dead_letter_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    args: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    kwargs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    replayed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
