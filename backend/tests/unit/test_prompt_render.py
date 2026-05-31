from types import SimpleNamespace

from app.services.prompt_service import PromptService


def test_render_user_prompt_substitutes_all_vars() -> None:
    template = (
        "Business: $business_name | "
        "Lang: $response_language | Rating: $review_rating | "
        "Comment: $review_comment | Tone: $tone_instructions | "
        "First name: $reviewer_first_name | Context: $business_context"
    )
    client = SimpleNamespace(
        business_name="Resto X",
        business_context="petit resto familial",
        tone_instructions="ton chaleureux",
    )
    settings = SimpleNamespace(language_override=None)
    review = SimpleNamespace(
        language="fr", rating=5, comment="Excellent !", reviewer_first_name="Alice"
    )

    service = PromptService.__new__(PromptService)  # bypass __init__ (no DB)
    out = service.render_user_prompt(
        template=template, client=client, settings=settings, review=review
    )
    assert "Resto X" in out
    assert "Lang: fr" in out
    assert "Rating: 5" in out
    assert "Excellent !" in out
    assert "Alice" in out
    assert "ton chaleureux" in out


def test_render_falls_back_to_settings_language_override() -> None:
    template = "$response_language"
    client = SimpleNamespace(business_name="X", business_context="", tone_instructions="")
    settings = SimpleNamespace(language_override="en")
    review = SimpleNamespace(language=None, rating=4, comment="ok", reviewer_first_name=None)
    service = PromptService.__new__(PromptService)
    out = service.render_user_prompt(
        template=template, client=client, settings=settings, review=review
    )
    assert out == "en"
