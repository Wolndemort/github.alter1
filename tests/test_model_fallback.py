import asyncio
from types import SimpleNamespace

from utils import ap_logic


def run(coro):
    return asyncio.run(coro)


def test_chat_fallback_uses_second_model(monkeypatch):
    calls = []

    async def create(**kwargs):
        calls.append(kwargs["model"])
        if len(calls) == 1:
            raise RuntimeError("primary down")
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    result = run(ap_logic.chat_with_fallback([{"role": "user", "content": "hi"}]))
    assert result.choices == []
    assert calls[0] == ap_logic.config.OPENROUTER_MODEL
    assert len(calls) == 2


def test_permanent_provider_error_does_not_waste_fallback_calls(monkeypatch):
    calls = []

    class ProviderLimit(Exception):
        status_code = 403

    async def create(**kwargs):
        calls.append(kwargs["model"])
        raise ProviderLimit("key limit")

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    try:
        run(ap_logic.chat_with_fallback([{"role": "user", "content": "hi"}]))
    except RuntimeError:
        pass
    assert len(calls) == 1


def test_complex_request_starts_with_reasoning_model():
    route = ap_logic.select_model_route([
        {"role": "user", "content": "Сравни архитектуры и составь подробный план миграции."},
    ])
    assert route[0] == ap_logic.config.OPENROUTER_REASONING_MODEL


def test_simple_request_uses_fast_model_first():
    route = ap_logic.select_model_route([{"role": "user", "content": "Привет, как дела?"}])
    assert route[0] == ap_logic.config.OPENROUTER_MODEL


def test_long_system_prompt_does_not_force_reasoning_route():
    route = ap_logic.select_model_route([
        {"role": "system", "content": "memory " * 1000},
        {"role": "user", "content": "Привет"},
    ])
    assert route[0] == ap_logic.config.OPENROUTER_MODEL


def test_tool_loop_preserves_tool_calls_and_returns_final_answer(monkeypatch):
    calls = []
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="get_weather", arguments='{"city":"Москва"}'),
    )
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tool_call]))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Готово", tool_calls=[]))]),
    ]

    async def create(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    async def weather(city):
        return {"city": city, "temperature": 20}

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    monkeypatch.setattr(ap_logic, "execute_tool", weather)
    result = run(ap_logic.chat_with_tools([{"role": "user", "content": "Погода?"}]))

    assert result.choices[0].message.content == "Готово"
    assert calls[1]["messages"][-2]["role"] == "assistant"
    assert calls[1]["messages"][-2]["tool_calls"][0]["id"] == "call-1"
    assert calls[1]["messages"][-1]["tool_call_id"] == "call-1"


def test_tool_failure_is_returned_to_model(monkeypatch):
    tool_call = SimpleNamespace(
        id="call-2",
        function=SimpleNamespace(name="get_weather", arguments="{}"),
    )
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tool_call]))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Ок", tool_calls=[]))]),
    ]

    async def create(**kwargs):
        return responses.pop(0)

    async def fail(*args, **kwargs):
        raise RuntimeError("weather down")

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    monkeypatch.setattr(ap_logic, "execute_tool", fail)
    result = run(ap_logic.chat_with_tools([{"role": "user", "content": "Погода?"}]))
    assert result.choices[0].message.content == "Ок"
