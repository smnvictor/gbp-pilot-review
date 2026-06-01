"""Test factories — synchronous helpers that build model instances.

These are deliberately not factory-boy classes: factory-boy's async support
requires an active session at factory-construction time which is awkward to
inject in many places. Instead we use plain helper functions that build (but
do not persist) model instances; callers add them to the session they own.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.models.client import Client
from app.models.client_settings import ClientSettings
from app.models.dead_letter_job import DeadLetterJob
from app.models.enums import (
    ClientStatus,
    LocationStatus,
    NoTextReviewPolicy,
    OAuthCredentialStatus,
    PublishDelayRange,
    ResponseSource,
    ResponseStatus,
    ReviewStatus,
    SubscriptionStatus,
    SubscriptionTier,
    UserRole,
    ValidationMode,
)
from app.models.location import Location
from app.models.notification_preference import NotificationPreference
from app.models.oauth_credential import OAuthCredential
from app.models.quota_usage import QuotaUsage
from app.models.response import Response
from app.models.review import Review
from app.models.subscription import Subscription
from app.models.user import User
from app.security.auth import hash_password


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def build_user(
    *,
    email: str | None = None,
    role: UserRole = UserRole.client,
    client_id: UUID | None = None,
    password: str = "Password123!",
) -> User:
    return User(
        email=email or f"{_unique('user')}@example.com",
        password_hash=hash_password(password),
        role=role,
        client_id=client_id,
        email_verified_at=datetime.now(UTC),
    )


def build_client(
    *,
    business_name: str = "Test Business",
    slug: str | None = None,
    status: ClientStatus = ClientStatus.active,
) -> Client:
    return Client(
        business_name=business_name,
        slug=slug or _unique("biz"),
        business_context="A friendly test business.",
        tone_instructions="Be warm and concise.",
        status=status,
    )


def build_client_settings(
    *,
    client_id: UUID,
    validation_mode: ValidationMode = ValidationMode.suggestion,
    no_text_policy: NoTextReviewPolicy = NoTextReviewPolicy.reply_4_5_only,
    publish_delay_range: PublishDelayRange = PublishDelayRange.range_1h_2h,
    regex_blocklist: list[str] | None = None,
) -> ClientSettings:
    return ClientSettings(
        client_id=client_id,
        validation_mode=validation_mode,
        no_text_review_policy=no_text_policy,
        publish_delay_range=publish_delay_range,
        regex_blocklist=regex_blocklist or [],
    )


def build_location(
    *,
    client_id: UUID,
    google_location_id: str | None = None,
    google_account_id: str = "12345",
) -> Location:
    return Location(
        client_id=client_id,
        google_account_id=google_account_id,
        google_location_id=google_location_id or _unique("loc"),
        name="Test Location",
        address="1 rue de Test",
        primary_category="restaurant",
        status=LocationStatus.active,
    )


def build_review(
    *,
    location_id: UUID,
    rating: int = 5,
    comment: str | None = "Service exceptionnel, je recommande chaleureusement !",
    google_review_id: str | None = None,
    status: ReviewStatus = ReviewStatus.detected,
    language: str | None = None,
) -> Review:
    now = datetime.now(UTC)
    return Review(
        location_id=location_id,
        google_review_id=google_review_id or _unique("rev"),
        reviewer_display_name="Jean Dupont",
        reviewer_first_name="Jean",
        rating=rating,
        comment=comment,
        language=language,
        posted_at=now,
        fetched_at=now,
        status=status,
    )


def build_response(
    *,
    review_id: UUID,
    content: str = "Merci pour votre avis !",
    status: ResponseStatus = ResponseStatus.pending_validation_client,
    source: ResponseSource = ResponseSource.ai,
    version: int = 1,
) -> Response:
    return Response(
        review_id=review_id,
        version=version,
        is_active=True,
        source=source,
        content=content,
        ai_status=1,
        ai_model="claude-sonnet-4-6",
        status=status,
    )


def build_subscription(
    *,
    client_id: UUID,
    tier: SubscriptionTier = SubscriptionTier.pro,
    status: SubscriptionStatus = SubscriptionStatus.active,
    monthly_quota: int = 50,
) -> Subscription:
    return Subscription(
        client_id=client_id,
        tier=tier,
        status=status,
        monthly_response_quota=monthly_quota,
    )


def build_oauth_credential(
    *,
    client_id: UUID,
    status: OAuthCredentialStatus = OAuthCredentialStatus.active,
    expires_in_seconds: int = 3600,
) -> OAuthCredential:
    return OAuthCredential(
        client_id=client_id,
        access_token_encrypted="access-token-plaintext",
        refresh_token_encrypted="refresh-token-plaintext",
        scopes=["https://www.googleapis.com/auth/business.manage"],
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
        status=status,
    )


def build_notification_preference(
    *, client_id: UUID, email: str = "alerts@example.com"
) -> NotificationPreference:
    return NotificationPreference(client_id=client_id, email_address=email)


def build_quota_usage(*, client_id: UUID, count: int = 0) -> QuotaUsage:
    now = datetime.now(UTC)
    return QuotaUsage(
        client_id=client_id,
        year_month=f"{now.year:04d}-{now.month:02d}",
        count=count,
    )


def build_dead_letter_job(
    *,
    task_name: str = "app.tasks.generation_tasks.generate_response",
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    last_error: str = "boom",
    attempts: int = 3,
) -> DeadLetterJob:
    return DeadLetterJob(
        task_name=task_name,
        args=args or [],
        kwargs=kwargs or {},
        last_error=last_error,
        attempts=attempts,
        failed_at=datetime.now(UTC),
    )


async def create_full_client(
    session: Any,
    *,
    business_name: str = "Test Business",
    tier: SubscriptionTier = SubscriptionTier.pro,
    validation_mode: ValidationMode = ValidationMode.suggestion,
) -> tuple[Client, User, ClientSettings, Subscription, Location, OAuthCredential]:
    """Persist a full client graph: client + user + settings + subscription + location + oauth."""
    client = build_client(business_name=business_name)
    session.add(client)
    await session.flush()

    user = build_user(client_id=client.id)
    settings = build_client_settings(client_id=client.id, validation_mode=validation_mode)
    subscription = build_subscription(client_id=client.id, tier=tier)
    location = build_location(client_id=client.id)
    credential = build_oauth_credential(client_id=client.id)
    pref = build_notification_preference(client_id=client.id, email=user.email)
    session.add_all([user, settings, subscription, location, credential, pref])
    await session.flush()
    return client, user, settings, subscription, location, credential


__all__ = [
    "build_client",
    "build_client_settings",
    "build_dead_letter_job",
    "build_location",
    "build_notification_preference",
    "build_oauth_credential",
    "build_quota_usage",
    "build_response",
    "build_review",
    "build_subscription",
    "build_user",
    "create_full_client",
]
