import pytest

from services.chat_service import validate_message


def test_chat_message_is_trimmed():
    assert validate_message("  привет  ") == "привет"


def test_chat_message_cannot_be_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_message("  ")


def test_chat_message_has_prompt_safety_limit(monkeypatch):
    from services import chat_service

    monkeypatch.setattr(chat_service.config, "AI_MAX_PROMPT_CHARS", 3)
    with pytest.raises(ValueError, match="too long"):
        validate_message("1234")
