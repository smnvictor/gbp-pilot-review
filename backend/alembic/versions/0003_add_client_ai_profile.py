"""Add AI personalization fields to clients (tone, always/never mention).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column(
            "tone",
            ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "clients",
        sa.Column("always_mention", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "clients",
        sa.Column("never_mention", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("clients", "never_mention")
    op.drop_column("clients", "always_mention")
    op.drop_column("clients", "tone")
