from app.utils.language import detect_language


def test_detect_french() -> None:
    assert detect_language("Le service était vraiment excellent et le personnel charmant !") == "fr"


def test_detect_english() -> None:
    assert (
        detect_language("The service was really excellent and the staff was so friendly!") == "en"
    )


def test_detect_empty_returns_none() -> None:
    assert detect_language("") is None
    assert detect_language("  ") is None
    assert detect_language("ab") is None  # < 3 chars
