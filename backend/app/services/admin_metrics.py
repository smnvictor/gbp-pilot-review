from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.dead_letter_job import DeadLetterJob
from app.models.enums import (
    ClientStatus,
    OAuthCredentialStatus,
    ResponseStatus,
)
from app.models.location import Location
from app.models.oauth_credential import OAuthCredential
from app.models.response import Response
from app.models.review import Review
from app.schemas.admin import AdminClientMetrics, AdminSystemMetrics


async def get_client_metrics(session: AsyncSession, client_id: UUID) -> AdminClientMetrics:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)

    reviews_total = (
        await session.scalar(
            select(func.count(Review.id))
            .join(Location, Location.id == Review.location_id)
            .where(Location.client_id == client_id, Review.deleted_at.is_(None))
        )
        or 0
    )

    reviews_30d = (
        await session.scalar(
            select(func.count(Review.id))
            .join(Location, Location.id == Review.location_id)
            .where(
                Location.client_id == client_id,
                Review.deleted_at.is_(None),
                Review.posted_at >= cutoff,
            )
        )
        or 0
    )

    published_total = (
        await session.scalar(
            select(func.count(Response.id))
            .join(Review, Review.id == Response.review_id)
            .join(Location, Location.id == Review.location_id)
            .where(
                Location.client_id == client_id,
                Response.status == ResponseStatus.published,
                Response.deleted_at.is_(None),
            )
        )
        or 0
    )

    published_30d = (
        await session.scalar(
            select(func.count(Response.id))
            .join(Review, Review.id == Response.review_id)
            .join(Location, Location.id == Review.location_id)
            .where(
                Location.client_id == client_id,
                Response.status == ResponseStatus.published,
                Response.deleted_at.is_(None),
                Response.published_at >= cutoff,
            )
        )
        or 0
    )

    last_review_at = await session.scalar(
        select(func.max(Review.posted_at))
        .join(Location, Location.id == Review.location_id)
        .where(Location.client_id == client_id, Review.deleted_at.is_(None))
    )

    last_published_at = await session.scalar(
        select(func.max(Response.published_at))
        .join(Review, Review.id == Response.review_id)
        .join(Location, Location.id == Review.location_id)
        .where(
            Location.client_id == client_id,
            Response.status == ResponseStatus.published,
        )
    )

    rate = (published_30d / reviews_30d) if reviews_30d else 0.0

    return AdminClientMetrics(
        client_id=client_id,
        reviews_total=reviews_total,
        reviews_30d=reviews_30d,
        responses_published_total=published_total,
        responses_published_30d=published_30d,
        response_rate_30d=round(rate, 4),
        last_review_at=last_review_at,
        last_published_at=last_published_at,
    )


async def get_system_metrics(session: AsyncSession) -> AdminSystemMetrics:
    now = datetime.now(UTC)
    cutoff_24h = now - timedelta(hours=24)

    active = (
        await session.scalar(
            select(func.count(Client.id)).where(
                Client.status == ClientStatus.active, Client.deleted_at.is_(None)
            )
        )
        or 0
    )
    suspended = (
        await session.scalar(
            select(func.count(Client.id)).where(
                Client.status == ClientStatus.suspended, Client.deleted_at.is_(None)
            )
        )
        or 0
    )
    paused = (
        await session.scalar(
            select(func.count(Client.id)).where(
                Client.status == ClientStatus.paused, Client.deleted_at.is_(None)
            )
        )
        or 0
    )

    published_24h = (
        await session.scalar(
            select(func.count(Response.id)).where(
                Response.status == ResponseStatus.published,
                Response.published_at >= cutoff_24h,
            )
        )
        or 0
    )

    pending = (
        await session.scalar(
            select(func.count(Response.id)).where(
                Response.status.in_(
                    [
                        ResponseStatus.pending_validation_client,
                        ResponseStatus.pending_validation_team,
                    ]
                ),
                Response.deleted_at.is_(None),
            )
        )
        or 0
    )

    dlq_depth = (
        await session.scalar(
            select(func.count(DeadLetterJob.id)).where(DeadLetterJob.replayed_at.is_(None))
        )
        or 0
    )

    oauth_alerts = (
        await session.scalar(
            select(func.count(OAuthCredential.id)).where(
                OAuthCredential.status.in_(
                    [
                        OAuthCredentialStatus.expiring,
                        OAuthCredentialStatus.expired,
                        OAuthCredentialStatus.revoked,
                    ]
                )
            )
        )
        or 0
    )

    return AdminSystemMetrics(
        active_clients=active,
        suspended_clients=suspended,
        paused_clients=paused,
        responses_published_24h=published_24h,
        pending_validation=pending,
        dlq_depth=dlq_depth,
        oauth_alerts=oauth_alerts,
    )
