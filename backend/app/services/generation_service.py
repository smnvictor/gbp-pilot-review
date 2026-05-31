from dataclasses import dataclass
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.claude.adapter import LLMProvider, LLMRequest, LLMResponse
from app.integrations.claude.client import ClaudeClient
from app.models.client import Client
from app.models.client_settings import ClientSettings
from app.models.enums import ResponseSource, ResponseStatus, ReviewStatus, ValidationMode
from app.models.prompt_version import PromptVersion
from app.models.response import Response
from app.models.review import Review
from app.repositories.client_settings_repository import ClientSettingsRepository
from app.repositories.location_repository import LocationRepository
from app.repositories.response_repository import ResponseRepository
from app.repositories.review_repository import ReviewRepository
from app.services.prompt_service import PromptService
from app.services.quota_service import QuotaExhaustedError, QuotaService


@dataclass
class PreviewResult:
    content: str
    ai_status: int
    ai_details: str | None
    tone: list[str]
    business_context: str


class GenerationService:
    def __init__(
        self,
        session: AsyncSession,
        provider: LLMProvider | None = None,
    ) -> None:
        self.session = session
        self.provider: LLMProvider = provider or ClaudeClient()
        self.reviews = ReviewRepository(session)
        self.responses = ResponseRepository(session)
        self.locations = LocationRepository(session)
        self.client_settings = ClientSettingsRepository(session)
        self.prompts = PromptService(session)
        self.quotas = QuotaService(session)

    async def generate_for_review(self, review_id: UUID) -> Response:
        review = await self.reviews.get(review_id)
        if review is None:
            raise ValueError(f"Review {review_id} not found")
        location = await self.locations.get(review.location_id)
        if location is None:
            raise ValueError(f"Location missing for review {review_id}")
        settings = await self.client_settings.get_by_client(location.client_id)
        if settings is None:
            raise ValueError(f"Settings missing for client {location.client_id}")

        try:
            await self.quotas.consume_or_raise(location.client_id)
        except QuotaExhaustedError:
            review.status = ReviewStatus.processing
            await self.session.commit()
            logger.warning("Quota exhausted for client {cid}", cid=location.client_id)
            raise

        version = await self.prompts.active_version()
        client = await self.session.get(Client, location.client_id)
        if client is None:
            raise ValueError(f"Client {location.client_id} not found")
        user_prompt = self.prompts.render_user_prompt(
            template=version.user_prompt_template,
            client=client,
            settings=settings,
            review=review,
        )

        try:
            llm_response = await self.provider.generate(
                LLMRequest(
                    system_prompt=version.system_prompt,
                    user_prompt=user_prompt,
                    model=version.model,
                    temperature=float(version.temperature),
                    max_tokens=version.max_tokens,
                )
            )
        except Exception as exc:
            logger.exception("LLM call failed for review {rid}", rid=review_id)
            llm_response = LLMResponse(
                status=0,
                content="",
                details="generation_error",
                tokens_input=0,
                tokens_output=0,
                model=version.model,
            )
            _ = exc

        next_status = self._route(settings, llm_response.status, llm_response.details)

        response = Response(
            review_id=review.id,
            version=1,
            is_active=True,
            source=ResponseSource.ai,
            content=llm_response.content,
            ai_status=llm_response.status,
            ai_details=llm_response.details or None,
            ai_model=llm_response.model,
            prompt_version_id=version.id,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            status=next_status,
        )
        self.session.add(response)
        review.status = ReviewStatus.awaiting_response
        await self.session.commit()
        await self.session.refresh(response)
        return response

    async def generate_preview(
        self,
        *,
        client: Client,
        settings: ClientSettings,
        review: Review,
        version: PromptVersion,
    ) -> PreviewResult:
        """Dry-run generation: no quota consumed, no DB write, nothing published."""
        user_prompt = self.prompts.render_user_prompt(
            template=version.user_prompt_template,
            client=client,
            settings=settings,
            review=review,
        )
        llm = await self.provider.generate(
            LLMRequest(
                system_prompt=version.system_prompt,
                user_prompt=user_prompt,
                model=version.model,
                temperature=float(version.temperature),
                max_tokens=version.max_tokens,
            )
        )
        return PreviewResult(
            content=llm.content,
            ai_status=llm.status,
            ai_details=llm.details or None,
            tone=client.tone or [],
            business_context=client.business_context or "",
        )

    @staticmethod
    def _route(settings: ClientSettings, ai_status: int, details: str | None) -> ResponseStatus:
        if ai_status == 0:
            # Refusal — always team review (hard rule from docs/04-flows.md)
            return ResponseStatus.pending_validation_team
        if details == "generation_error":
            return ResponseStatus.pending_validation_team
        return (
            ResponseStatus.pending_validation_team
            if settings.validation_mode == ValidationMode.team
            else ResponseStatus.pending_validation_client
        )
