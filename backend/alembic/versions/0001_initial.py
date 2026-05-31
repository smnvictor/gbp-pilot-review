"""Initial schema — 16 tables.

Revision ID: 0001
Revises:
Create Date: 2026-04-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


user_role = postgresql.ENUM("client", "admin", name="user_role", create_type=False)
client_status = postgresql.ENUM(
    "active", "paused", "suspended", name="client_status", create_type=False
)
subscription_tier = postgresql.ENUM(
    "starter", "pro", "business", name="subscription_tier", create_type=False
)
subscription_status = postgresql.ENUM(
    "trial",
    "active",
    "past_due",
    "cancelled",
    "expired",
    name="subscription_status",
    create_type=False,
)
oauth_credential_status = postgresql.ENUM(
    "active",
    "expiring",
    "expired",
    "revoked",
    name="oauth_credential_status",
    create_type=False,
)
location_status = postgresql.ENUM("active", "paused", name="location_status", create_type=False)
review_status = postgresql.ENUM(
    "detected",
    "filtering",
    "blocked_regex",
    "requires_human_validation",
    "processing",
    "awaiting_response",
    "completed",
    name="review_status",
    create_type=False,
)
response_status = postgresql.ENUM(
    "draft",
    "pending_validation_client",
    "pending_validation_team",
    "awaiting_publication",
    "scheduled",
    "publishing",
    "published",
    "failed",
    "cancelled",
    "superseded",
    name="response_status",
    create_type=False,
)
response_source = postgresql.ENUM(
    "ai",
    "manual_validator",
    "manual_client",
    name="response_source",
    create_type=False,
)
publish_delay_range = postgresql.ENUM(
    "1h_2h",
    "2h_5h",
    "5h_1d",
    "1d_2d",
    "2d_5d",
    name="publish_delay_range",
    create_type=False,
)
no_text_review_policy = postgresql.ENUM(
    "ignore",
    "reply_4_5_only",
    "reply_all",
    name="no_text_review_policy",
    create_type=False,
)
validation_mode = postgresql.ENUM("suggestion", "team", name="validation_mode", create_type=False)
notification_channel = postgresql.ENUM(
    "email", "telegram", "sms", name="notification_channel", create_type=False
)
notification_status = postgresql.ENUM(
    "pending",
    "deferred",
    "sent",
    "failed",
    name="notification_status",
    create_type=False,
)


ALL_ENUMS = [
    user_role,
    client_status,
    subscription_tier,
    subscription_status,
    oauth_credential_status,
    location_status,
    review_status,
    response_status,
    response_source,
    publish_delay_range,
    no_text_review_policy,
    validation_mode,
    notification_channel,
    notification_status,
]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    for e in ALL_ENUMS:
        e.create(bind, checkfirst=True)

    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("business_name", sa.String, nullable=False),
        sa.Column("slug", sa.String, nullable=False),
        sa.Column("business_context", sa.Text, nullable=False, server_default=""),
        sa.Column("tone_instructions", sa.Text, nullable=False, server_default=""),
        sa.Column("status", client_status, nullable=False, server_default="active"),
        sa.Column("onboarding_completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True)),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_clients_status", "clients", ["status"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="client"),
        sa.Column("email_verified_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True)),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_client_id", "users", ["client_id"])

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tier", subscription_tier, nullable=False),
        sa.Column("status", subscription_status, nullable=False),
        sa.Column("lemonsqueezy_subscription_id", sa.String),
        sa.Column("lemonsqueezy_customer_id", sa.String),
        sa.Column("trial_ends_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("current_period_start", sa.TIMESTAMP(timezone=True)),
        sa.Column("current_period_end", sa.TIMESTAMP(timezone=True)),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("monthly_response_quota", sa.Integer, nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("client_id", name="uq_subscriptions_client"),
    )
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index(
        "uq_subscriptions_lemonsqueezy_id",
        "subscriptions",
        ["lemonsqueezy_subscription_id"],
        unique=True,
        postgresql_where=sa.text("lemonsqueezy_subscription_id IS NOT NULL"),
    )

    op.create_table(
        "quota_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year_month", sa.CHAR(7), nullable=False),
        sa.Column("count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_alert_threshold", sa.Integer),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("client_id", "year_month", name="uq_quota_client_month"),
    )

    op.create_table(
        "oauth_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_token_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("refresh_token_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String), nullable=False),
        sa.Column("google_account_id", sa.String),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", oauth_credential_status, nullable=False, server_default="active"),
        sa.Column("last_refreshed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_check_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("client_id", name="uq_oauth_client"),
    )
    op.create_index("ix_oauth_status_expiry", "oauth_credentials", ["status", "expires_at"])

    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("google_account_id", sa.String, nullable=False),
        sa.Column("google_location_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("address", sa.Text),
        sa.Column("primary_category", sa.String),
        sa.Column("status", location_status, nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("google_location_id", name="uq_locations_google_id"),
    )
    op.create_index("ix_locations_client_status", "locations", ["client_id", "status"])

    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("google_review_id", sa.String, nullable=False),
        sa.Column("reviewer_display_name", sa.String),
        sa.Column("reviewer_first_name", sa.String),
        sa.Column("rating", sa.SmallInteger, nullable=False),
        sa.Column("comment", sa.Text),
        sa.Column("language", sa.CHAR(2)),
        sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_edited_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "parent_review_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reviews.id"),
        ),
        sa.Column("status", review_status, nullable=False, server_default="detected"),
        sa.Column("block_reason", sa.Text),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating_range"),
        sa.UniqueConstraint("google_review_id", name="uq_reviews_google_id"),
    )
    op.create_index(
        "ix_reviews_location_posted_at",
        "reviews",
        ["location_id", sa.text("posted_at DESC")],
    )
    op.create_index("ix_reviews_status_location", "reviews", ["status", "location_id"])
    op.create_index(
        "ix_reviews_parent",
        "reviews",
        ["parent_review_id"],
        postgresql_where=sa.text("parent_review_id IS NOT NULL"),
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String, nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("user_prompt_template", sa.Text, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=False, server_default="0.70"),
        sa.Column("max_tokens", sa.Integer, nullable=False, server_default="600"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("version", name="uq_prompt_version"),
    )
    op.create_index(
        "uq_prompt_active",
        "prompt_versions",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "review_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.SmallInteger, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("source", response_source, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("ai_status", sa.SmallInteger),
        sa.Column("ai_details", sa.Text),
        sa.Column("ai_model", sa.Text),
        sa.Column(
            "prompt_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_versions.id"),
        ),
        sa.Column("tokens_input", sa.Integer),
        sa.Column("tokens_output", sa.Integer),
        sa.Column("status", response_status, nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("undo_deadline_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("failed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("failure_reason", sa.Text),
        sa.Column(
            "validated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("validated_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True)),
        sa.UniqueConstraint("review_id", "version", name="uq_response_review_version"),
    )
    op.create_index(
        "ix_response_active_review",
        "responses",
        ["review_id"],
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "ix_response_scheduled",
        "responses",
        ["status", "scheduled_at"],
        postgresql_where=sa.text("status = 'scheduled'"),
    )
    op.create_index(
        "ix_response_pending",
        "responses",
        ["status"],
        postgresql_where=sa.text(
            "status IN ('pending_validation_client','pending_validation_team')"
        ),
    )

    op.create_table(
        "regenerations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "review_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_regenerations_review_created", "regenerations", ["review_id", "created_at"])

    op.create_table(
        "client_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("polling_frequency_minutes", sa.Integer, nullable=False, server_default="1440"),
        sa.Column(
            "publish_delay_range", publish_delay_range, nullable=False, server_default="1d_2d"
        ),
        sa.Column("publish_window_start", sa.Time, nullable=False, server_default="09:00"),
        sa.Column("publish_window_end", sa.Time, nullable=False, server_default="21:00"),
        sa.Column(
            "publish_window_timezone", sa.String, nullable=False, server_default="Europe/Paris"
        ),
        sa.Column("language_override", sa.CHAR(2)),
        sa.Column(
            "no_text_review_policy",
            no_text_review_policy,
            nullable=False,
            server_default="reply_4_5_only",
        ),
        sa.Column("validation_mode", validation_mode, nullable=False, server_default="suggestion"),
        sa.Column("digest_mode", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("digest_hour", sa.SmallInteger, nullable=False, server_default="9"),
        sa.Column(
            "regex_blocklist",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "publish_window_end > publish_window_start", name="ck_publish_window_order"
        ),
        sa.UniqueConstraint("client_id", name="uq_client_settings_client"),
    )

    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "primary_channel",
            notification_channel,
            nullable=False,
            server_default="email",
        ),
        sa.Column("email_address", sa.String),
        sa.Column("telegram_chat_id", sa.String),
        sa.Column("telegram_verified_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("sms_phone", sa.String),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("client_id", name="uq_notif_pref_client"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("channel", notification_channel, nullable=False),
        sa.Column("template_code", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", notification_status, nullable=False),
        sa.Column(
            "related_review_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reviews.id"),
        ),
        sa.Column(
            "related_response_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("responses.id"),
        ),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("failed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("error", sa.Text),
        sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_notifications_client_created",
        "notifications",
        ["client_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_notifications_pending",
        "notifications",
        ["status"],
        postgresql_where=sa.text("status IN ('pending','deferred')"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text, nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_audit_target",
        "audit_logs",
        ["target_type", "target_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_audit_actor",
        "audit_logs",
        ["actor_user_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "dead_letter_jobs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("task_name", sa.Text, nullable=False),
        sa.Column("args", postgresql.JSONB, nullable=False),
        sa.Column("kwargs", postgresql.JSONB, nullable=False),
        sa.Column("last_error", sa.Text, nullable=False),
        sa.Column("traceback", sa.Text),
        sa.Column("attempts", sa.SmallInteger, nullable=False),
        sa.Column("failed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("replayed_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index(
        "ix_dlq_task_failed",
        "dead_letter_jobs",
        ["task_name", sa.text("failed_at DESC")],
    )
    op.create_index(
        "ix_dlq_unreplayed",
        "dead_letter_jobs",
        ["replayed_at"],
        postgresql_where=sa.text("replayed_at IS NULL"),
    )

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.Text, nullable=False, server_default="lemonsqueezy"),
        sa.Column("event_id", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column(
            "received_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("processing_error", sa.Text),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("webhook_events")
    op.drop_table("dead_letter_jobs")
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("notification_preferences")
    op.drop_table("client_settings")
    op.drop_table("regenerations")
    op.drop_table("responses")
    op.drop_table("prompt_versions")
    op.drop_table("reviews")
    op.drop_table("locations")
    op.drop_table("oauth_credentials")
    op.drop_table("quota_usage")
    op.drop_table("subscriptions")
    op.drop_table("users")
    op.drop_table("clients")
    for e in reversed(ALL_ENUMS):
        e.drop(bind, checkfirst=True)
