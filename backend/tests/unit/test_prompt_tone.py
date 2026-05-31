from app.models.client import Client
from app.services.prompt_service import TONE_LABELS, _tone_instructions


def test_tone_instructions_maps_structured_tones() -> None:
    client = Client(tone=["Professionnel", "Concis"], tone_instructions="")
    result = _tone_instructions(client)
    assert TONE_LABELS["Professionnel"] in result
    assert TONE_LABELS["Concis"] in result


def test_tone_instructions_appends_free_text() -> None:
    client = Client(tone=["Chaleureux"], tone_instructions="Signez « Marie ».")
    result = _tone_instructions(client)
    assert TONE_LABELS["Chaleureux"] in result
    assert "Signez « Marie »." in result


def test_tone_instructions_empty() -> None:
    client = Client(tone=[], tone_instructions="")
    assert _tone_instructions(client) == ""
