import enum
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_settings import ClientSettings
from app.models.enums import (
    NoTextReviewPolicy,
    ResponseSource,
    ResponseStatus,
    ReviewStatus,
    ValidationMode,
)
from app.models.response import Response
from app.models.review import Review
from app.repositories.client_settings_repository import ClientSettingsRepository
from app.repositories.location_repository import LocationRepository
from app.repositories.review_repository import ReviewRepository
from app.utils.language import detect_language

NO_TEXT_TEMPLATES: dict[str, dict[int, str]] = {
    "fr": {
        5: "Merci pour votre note 5 étoiles ! Au plaisir de vous accueillir à nouveau.",
        4: "Merci pour votre note ! Nous espérons vous revoir bientôt.",
        3: "Merci pour votre retour. N'hésitez pas à nous partager vos impressions.",
    },
    "en": {
        5: "Thanks for the 5-star rating! We look forward to seeing you again.",
        4: "Thanks for your rating! Hope to see you soon.",
        3: "Thanks for your feedback. Feel free to share more about your experience.",
    },
}


class FilterDecision(enum.Enum):
    BLOCKED_REGEX = "blocked_regex"
    REQUIRES_HUMAN = "requires_human_validation"
    BYPASS_NO_TEXT = "bypass_no_text"
    PROCESSING = "processing"
    IGNORED = "ignored"


class FilteringService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reviews = ReviewRepository(session)
        self.locations = LocationRepository(session)
        self.client_settings = ClientSettingsRepository(session)

    async def decide(self, review_id: UUID) -> FilterDecision:
        review = await self.reviews.get(review_id)
        if review is None:
            raise ValueError(f"Review {review_id} not found")

        location = await self.locations.get(review.location_id)
        if location is None:
            raise ValueError(f"Location {review.location_id} missing")

        settings = await self.client_settings.get_by_client(location.client_id)
        if settings is None:
            raise ValueError(f"Settings for client {location.client_id} missing")

        review.status = ReviewStatus.filtering
        await self.session.flush()

        # 1. Empty text branch
        if not review.comment or not review.comment.strip():
            decision = self._handle_no_text(review, settings)
            await self.session.commit()
            return decision

        # 2. Regex blocklist
        for pattern in settings.regex_blocklist:
            try:
                if re.search(pattern, review.comment, flags=re.IGNORECASE):
                    review.status = ReviewStatus.blocked_regex
                    review.block_reason = f"Matched pattern: {pattern}"
                    await self.session.commit()
                    return FilterDecision.BLOCKED_REGEX
            except re.error:
                continue

        # 3. Language detection
        lang = settings.language_override or detect_language(review.comment)
        review.language = lang
        if lang not in {"fr", "en"}:
            review.status = ReviewStatus.requires_human_validation
            await self.session.commit()
            return FilterDecision.REQUIRES_HUMAN

        # 4. Note 1-3 → mandatory human validation
        if review.rating <= 3:
            review.status = ReviewStatus.requires_human_validation
            await self.session.commit()
            return FilterDecision.REQUIRES_HUMAN

        # 5. Continue to AI generation
        review.status = ReviewStatus.processing
        await self.session.commit()
        return FilterDecision.PROCESSING

    def _handle_no_text(self, review: Review, settings: ClientSettings) -> FilterDecision:
        policy = settings.no_text_review_policy
        if policy == NoTextReviewPolicy.ignore:
            review.status = ReviewStatus.completed
            return FilterDecision.IGNORED

        if policy == NoTextReviewPolicy.reply_4_5_only and review.rating < 4:
            review.status = ReviewStatus.completed
            return FilterDecision.IGNORED

        # Bypass IA: insert a templated response directly.
        lang = settings.language_override or "fr"
        templates = NO_TEXT_TEMPLATES.get(lang, NO_TEXT_TEMPLATES["fr"])
        text = templates.get(review.rating, templates[5])

        next_status = (
            ResponseStatus.pending_validation_team
            if settings.validation_mode == ValidationMode.team
            else ResponseStatus.pending_validation_client
        )

        response = Response(
            review_id=review.id,
            version=1,
            is_active=True,
            source=ResponseSource.ai,
            content=text,
            ai_model="template_no_text_v1",
            status=next_status,
        )
        self.session.add(response)
        review.status = ReviewStatus.awaiting_response
        review.language = lang
        return FilterDecision.BYPASS_NO_TEXT
