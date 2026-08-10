from services.voice_commands import (
    is_voice_change_request,
    is_voice_generation_request,
    requested_voice_id,
    voice_description,
)


def test_voice_commands_are_understood_in_text_and_voice_transcripts():
    assert is_voice_generation_request("Создай спокойный голос для подкаста")
    assert is_voice_change_request("Измени мой голос на созданный")
    assert voice_description("создай голос: низкий и спокойный") == "низкий и спокойный"


def test_voice_id_prefers_explicit_then_saved_then_default():
    assert requested_voice_id("измени голос voice_id=abc123", "saved", "default") == "abc123"
    assert requested_voice_id("измени мой голос", "saved", "default") == "saved"
    assert requested_voice_id("измени мой голос", None, "default") == "default"
