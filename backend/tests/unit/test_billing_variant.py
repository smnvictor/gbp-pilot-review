from app.config import Settings


def _settings() -> Settings:
    # model_construct skips validation so we don't need every required field;
    # lemonsqueezy_variant_for_tier only reads the three variant attributes.
    return Settings.model_construct(
        lemonsqueezy_variant_starter="111",
        lemonsqueezy_variant_pro="222",
        lemonsqueezy_variant_business="333",
    )


def test_variant_resolves_per_tier() -> None:
    settings = _settings()
    assert settings.lemonsqueezy_variant_for_tier("starter") == "111"
    assert settings.lemonsqueezy_variant_for_tier("pro") == "222"
    assert settings.lemonsqueezy_variant_for_tier("business") == "333"


def test_variant_unknown_or_unconfigured_returns_empty() -> None:
    settings = _settings()
    assert settings.lemonsqueezy_variant_for_tier("enterprise") == ""

    unconfigured = Settings.model_construct(
        lemonsqueezy_variant_starter="",
        lemonsqueezy_variant_pro="",
        lemonsqueezy_variant_business="",
    )
    assert unconfigured.lemonsqueezy_variant_for_tier("pro") == ""
