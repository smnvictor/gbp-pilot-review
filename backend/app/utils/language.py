from functools import lru_cache

from lingua import IsoCode639_1, Language, LanguageDetectorBuilder

_SUPPORTED = [
    Language.FRENCH,
    Language.ENGLISH,
    Language.SPANISH,
    Language.GERMAN,
    Language.ITALIAN,
]


@lru_cache(maxsize=1)
def _detector() -> object:
    return LanguageDetectorBuilder.from_languages(*_SUPPORTED).build()


def detect_language(text: str) -> str | None:
    """Return ISO 639-1 two-letter code, or None if undetermined."""
    if not text or len(text.strip()) < 3:
        return None
    detector = _detector()
    lang = detector.detect_language_of(text)  # type: ignore[attr-defined]
    if lang is None:
        return None
    iso: IsoCode639_1 = lang.iso_code_639_1
    return iso.name.lower()
