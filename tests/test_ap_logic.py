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


def test_tool_definitions_are_present():
    names = {item["function"]["name"] for item in ap_logic.TOOL_DEFINITIONS}
    assert {"web_search", "get_weather", "youtube_search"} <= names
