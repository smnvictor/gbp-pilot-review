from string import Template

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.client_settings import ClientSettings
from app.models.prompt_version import PromptVersion
from app.models.review import Review
from app.repositories.prompt_version_repository import PromptVersionRepository

TONE_LABELS: dict[str, str] = {
    "Professionnel": "ton professionnel, formel et neutre, vouvoiement systématique",
    "Chaleureux": "ton chaleureux, humain et empathique, remerciement appuyé",
    "Concis": "ton concis, court et factuel, droit au but",
}


def _tone_instructions(client: Client) -> str:
    parts = [TONE_LABELS.get(t, t) for t in (client.tone or [])]
    structured = " ; ".join(parts)
    free = client.tone_instructions or ""
    return "\n".join(p for p in (structured, free) if p)


class PromptService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.versions = PromptVersionRepository(session)

    async def active_version(self) -> PromptVersion:
        version = await self.versions.get_active()
        if version is None:
            raise RuntimeError("No active prompt_version — seed v1.0.0 in DB")
        return version

    def render_user_prompt(
        self,
        *,
        template: str,
        client: Client,
        settings: ClientSettings,
        review: Review,
    ) -> str:
        return Template(template).safe_substitute(
            business_name=client.business_name,
            business_context=client.business_context or "",
            tone_instructions=_tone_instructions(client),
            always_mention=client.always_mention or "",
            never_mention=client.never_mention or "",
            response_language=review.language or settings.language_override or "fr",
            review_rating=str(review.rating),
            review_comment=review.comment or "",
            reviewer_first_name=review.reviewer_first_name or "",
        )
