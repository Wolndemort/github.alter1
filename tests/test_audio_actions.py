import asyncio

from utils.audio_actions import AudioActionUnavailableError, detect_audio_action, effect_prompt, process_audio_action


def test_audio_actions_are_detected_from_natural_language():
    assert detect_audio_action("Создай звук дождя по стеклу") == "effect"
    assert detect_audio_action("Наложи звук леса на моё голосовое") == "mix"
    assert detect_audio_action("Почисти мою запись от шума") == "isolate"
    assert detect_audio_action("Что ты умеешь?") is None


def test_effect_prompt_keeps_the_subject():
    assert "дождя" in effect_prompt("Создай звук дождя по стеклу")


def test_sound_effect_action_returns_provider_audio(monkeypatch):
    async def fake_effect(prompt):
        assert "дождя" in prompt
        return b"mp3"

    monkeypatch.setattr("utils.audio_actions.sound_effect", fake_effect)
    result = asyncio.run(process_audio_action("создай звук дождя", b""))
    assert result == ("Создал звуковой эффект.", b"mp3")


def test_unavailable_audio_isolation_is_not_called_from_natural_language():
    try:
        asyncio.run(process_audio_action("почисти запись от шума", b"audio"))
    except AudioActionUnavailableError as exc:
        assert "недоступна" in str(exc)
    else:
        raise AssertionError("Audio Isolation must remain unavailable for the current provider key")
