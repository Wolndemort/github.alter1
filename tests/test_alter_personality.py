from utils.prompts import (
    ALTER_CHARACTER_PROMPT,
    ALTER_INTELLIGENCE_PROMPT,
    MEDIA_SYSTEM_PROMPT,
    PUBLIC_RESPONSE_POLICY,
)


def test_alter_character_is_conversational_and_decisive():
    assert "живой собеседник" in ALTER_CHARACTER_PROMPT
    assert "Не вываливай десять вариантов" in ALTER_CHARACTER_PROMPT
    assert "коротко и по-человечески" in ALTER_CHARACTER_PROMPT
    assert "мягко укажи на противоречие" in ALTER_CHARACTER_PROMPT


def test_alter_intelligence_turns_context_into_action():
    assert "Определи тип запроса" in ALTER_INTELLIGENCE_PROMPT
    assert "первый шаг" in ALTER_INTELLIGENCE_PROMPT
    assert "незавершённой темы" in ALTER_INTELLIGENCE_PROMPT


def test_media_route_uses_same_alter_voice():
    assert ALTER_CHARACTER_PROMPT in MEDIA_SYSTEM_PROMPT
    assert ALTER_INTELLIGENCE_PROMPT in MEDIA_SYSTEM_PROMPT


def test_public_policy_allows_conversational_russian():
    assert "разговорным русским языком" in PUBLIC_RESPONSE_POLICY
    assert "без формального отчёта" in PUBLIC_RESPONSE_POLICY
