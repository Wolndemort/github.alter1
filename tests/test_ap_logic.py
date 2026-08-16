import asyncio
from types import SimpleNamespace

from utils import ap_logic


def run(coro):
    return asyncio.run(coro)


def fake_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_summarize_parses_plain_json(monkeypatch):
    async def create(**kwargs):
        return fake_response('{"identity": {"name": "Adam"}}')

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    assert run(ap_logic.summarize_session([{"role": "user", "content": "Меня зовут Адам"}])) == {"identity": {"name": "Adam"}}


def test_summarize_parses_json_with_markdown(monkeypatch):
    async def create(**kwargs):
        return fake_response("```json\n{\"food_drinks\": {\"favorite_food\": [\"пицца\"]}}\n```")

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    result = run(ap_logic.summarize_session([]))
    assert result["food_drinks"]["favorite_food"] == ["пицца"]


def test_summarize_returns_empty_dict_on_invalid_response(monkeypatch):
    async def create(**kwargs):
        return fake_response("I cannot produce JSON")

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    assert run(ap_logic.summarize_session([])) == {}


def test_generate_reply_includes_memory_and_avoids_repetition_instruction(monkeypatch):
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return fake_response("Короткий ответ")

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    result = run(ap_logic.generate_reply([], {"identity": {"name": "Adam"}}))

    assert result == "Короткий ответ"
    system_prompt = captured["messages"][0]["content"]
    assert "Adam" in system_prompt
    assert "Не повторяй факты" in system_prompt


def test_generate_reply_keeps_recent_topic_and_memory_in_prompt_tail(monkeypatch):
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return fake_response("short reply")

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    monkeypatch.setattr(ap_logic.config, "AI_MAX_PROMPT_CHARS", 1200)
    run(ap_logic.generate_reply([
        {"role": "user", "content": "Собери билд на максимальный урон"},
        {"role": "assistant", "content": "Подберу оружие и обереги."},
        {"role": "user", "content": "И что по билду?"},
    ], {"identity": {"name": "Adam"}}, conversation_summary="Тема: билд на максимальный урон; следующий шаг: выбрать обереги."))

    system_prompt = captured["messages"][0]["content"]
    assert "ACTIVE CONVERSATION SUMMARY" in system_prompt
    assert "выбрать обереги" in system_prompt
    assert any("И что по билду?" in item.get("content", "") for item in captured["messages"])
    assert "Adam" in system_prompt


def test_recent_conversation_messages_keeps_six_latest_pairs():
    messages = [
        {"role": role, "content": f"{role}-{index}"}
        for index in range(10)
        for role in ("user", "assistant")
    ]
    recent = ap_logic.recent_conversation_messages(messages)
    assert len(recent) == 12
    assert recent[0]["content"] == "user-4"
    assert recent[-1]["content"] == "assistant-9"


def test_active_context_summary_is_plain_bounded_text(monkeypatch):
    async def fake_chat(*args, **kwargs):
        return fake_response("Цель: собрать билд. Следующий шаг: выбрать обереги.")

    monkeypatch.setattr(ap_logic, "chat_with_fallback", fake_chat)
    result = run(ap_logic.summarize_active_context([
        {"role": "user", "content": "Собери билд на максимальный урон"},
    ]))
    assert result == "Цель: собрать билд. Следующий шаг: выбрать обереги."
    assert len(result) <= 1200


def test_tool_definitions_are_present():
    names = {item["function"]["name"] for item in ap_logic.TOOL_DEFINITIONS}
    assert {"web_search", "get_weather", "youtube_search"} <= names


def test_long_list_requests_get_a_larger_output_budget(monkeypatch):
    monkeypatch.setattr(ap_logic.config, "MAX_OUTPUT_TOKENS", 600)
    monkeypatch.setattr(ap_logic.config, "LONG_REPLY_MAX_OUTPUT_TOKENS", 1200)
    assert ap_logic._response_token_budget([{"role": "user", "content": "show a full list of all items"}], None, None) == 1200
    assert ap_logic._response_token_budget([{"role": "user", "content": "hi"}], None, None) == 320


def test_valid_long_reply_is_not_replaced_by_short_fallback(monkeypatch):
    long_reply = "Пункт списка. " * 300

    async def create(**kwargs):
        return fake_response(long_reply)

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    assert run(ap_logic.generate_reply([], {"identity": {"name": "Adam"}})) == long_reply.strip()
