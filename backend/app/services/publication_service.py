from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations.google_business.adapter import GoogleBusinessAdapter
from app.integrations.google_business.client import GoogleBusinessClient
from app.integrations.google_business.exceptions import GoogleAuthError
from app.models.enums import (
    OAuthCredentialStatus,
    ResponseStatus,
    ReviewStatus,
)
from app.models.response import Response
from app.repositories.client_settings_repository import ClientSettingsRepository
from app.repositories.location_repository import LocationRepository
from app.repositories.oauth_repository import OAuthRepository
from app.repositories.response_repository import ResponseRepository
from app.repositories.review_repository import ReviewRepository
from app.utils.time import compute_publish_at


class PublicationService:
    def __init__(
        self,
        session: AsyncSession,
        adapter: GoogleBusinessAdapter | None = None,
    ) -> None:
        self.session = session
        self.adapter: GoogleBusinessAdapter = adapter or GoogleBusinessClient()
        self.responses = ResponseRepository(session)
        self.reviews = ReviewRepository(session)
        self.locations = LocationRepository(session)
        self.client_settings = ClientSettingsRepository(session)
        self.oauth = OAuthRepository(session)

    async def schedule_publication(self, response_id: UUID, validated_by_user_id: UUID) -> Response:
        response = await self.responses.get(response_id)
        if response is None:
            raise HTTPException(404, "Response not found")
        if response.status not in (
            ResponseStatus.pending_validation_client,
            ResponseStatus.pending_validation_team,
            ResponseStatus.draft,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot schedule from status {response.status.value}",
            )

        review = await self.reviews.get(response.review_id)
        if review is None:
            raise HTTPException(500, "Review missing")
        location = await self.locations.get(review.location_id)
        if location is None:
            raise HTTPException(500, "Location missing")
        settings = await self.client_settings.get_by_client(location.client_id)
        if settings is None:
            raise HTTPException(500, "Client settings missing")

        cfg = get_settings()
        now = datetime.now(UTC)
        scheduled_at = compute_publish_at(
            now=now,
            delay_range=settings.publish_delay_range,
            window_start=settings.publish_window_start,
            window_end=settings.publish_window_end,
            timezone=settings.publish_window_timezone,
        )
        response.status = ResponseStatus.scheduled
        response.scheduled_at = scheduled_at
        response.undo_deadline_at = now + timedelta(minutes=cfg.undo_grace_period_minutes)
        response.validated_by_user_id = validated_by_user_id
        response.validated_at = now
        await self.session.commit()
        return response

    async def cancel_publication(self, response_id: UUID) -> Response:
        response = await self.responses.get(response_id)
        if response is None:
            raise HTTPException(404, "Response not found")
        if response.status != ResponseStatus.scheduled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not scheduled (status={response.status.value})",
            )
        if response.undo_deadline_at is None or response.undo_deadline_at <= datetime.now(UTC):
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Undo window expired")
        response.status = ResponseStatus.cancelled
        response.is_active = False
        await self.session.commit()
        return response

    async def publish_now(self, response: Response) -> Response:
        """Called by the Celery worker once scheduled_at is reached."""
        if response.status != ResponseStatus.scheduled:
            return response
        if response.undo_deadline_at and response.undo_deadline_at > datetime.now(UTC):
            # Still in undo window — defer
            return response

        review = await self.reviews.get(response.review_id)
        if review is None:
            raise RuntimeError("Review missing for response")
        location = await self.locations.get(review.location_id)
        if location is None:
            raise RuntimeError("Location missing for response")
        credential = await self.oauth.get_by_client(location.client_id)
        if credential is None or credential.status != OAuthCredentialStatus.active:
            response.failure_reason = "OAuth credential unavailable"
            await self.session.commit()
            return response

        review_name = (
            f"accounts/{location.google_account_id}"
            f"/locations/{location.google_location_id}/reviews/{review.google_review_id}"
        )
        response.status = ResponseStatus.publishing
        await self.session.commit()
        try:
            await self.adapter.reply_to_review(
                credential.access_token_encrypted, review_name, response.content
            )
        except GoogleAuthError as exc:
            # Per docs/04-flows.md: rollback to scheduled, mark OAuth revoked, notify.
            credential.status = OAuthCredentialStatus.revoked
            response.status = ResponseStatus.scheduled
            response.failure_reason = f"OAuth revoked: {exc}"
            await self.session.commit()
            logger.warning(
                "Publication rolled back: OAuth revoked for response {rid}", rid=response.id
            )
            return response
        except Exception as exc:
            response.status = ResponseStatus.failed
            response.failed_at = datetime.now(UTC)
            response.failure_reason = str(exc)[:500]
            await self.session.commit()
            raise

        response.status = ResponseStatus.published
        response.published_at = datetime.now(UTC)
        review.status = ReviewStatus.completed
        await self.session.commit()
        return response
