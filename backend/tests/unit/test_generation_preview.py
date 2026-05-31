from decimal import Decimal

import pytest

from app.integrations.claude.adapter import LLMRequest, LLMResponse
from app.models.client import Client
from app.models.client_settings import ClientSettings
from app.models.prompt_version import PromptVersion
from app.models.review import Review
from app.services.generation_service import GenerationService


class _StubProvider:
    def __init__(self) -> None:
        self.calls: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(
            status=1,
            content="Merci pour votre retour !",
            details="",
            tokens_input=10,
            tokens_output=5,
            model="stub",
        )


def _version() -> PromptVersion:
    return PromptVersion(
        version="test",
        system_prompt="sys",
        user_prompt_template="$business_name / $tone_instructions / $review_comment",
        model="stub",
        temperature=Decimal("0.7"),
        max_tokens=100,
    )


@pytest.mark.asyncio
async def test_generate_preview_has_no_side_effects() -> None:
    provider = _StubProvider()
    service = GenerationService(session=None, provider=provider)  # type: ignore[arg-type]
    client = Client(business_name="Café Lou", tone=["Chaleureux"], business_context="ctx")
    settings = ClientSettings()
    review = Review(rating=5, comment="Super accueil")

    result = await service.generate_preview(
        client=client, settings=settings, review=review, version=_version()
    )

    assert result.content == "Merci pour votre retour !"
    assert result.ai_status == 1
    assert result.tone == ["Chaleureux"]
    assert result.business_context == "ctx"
    assert "Super accueil" in provider.calls[0].user_prompt
