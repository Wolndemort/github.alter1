import asyncio
from types import SimpleNamespace

from utils import ap_logic


def run(coro):
    return asyncio.run(coro)


def test_chat_fallback_uses_second_model(monkeypatch):
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_ALLOW_PAID_FALLBACK", True)
    calls = []

    async def create(**kwargs):
        calls.append(kwargs["model"])
        if len(calls) == 1:
            raise RuntimeError("primary down")
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    result = run(ap_logic.chat_with_fallback([{"role": "user", "content": "hi"}]))
    assert result.choices == []
    assert calls[0] == ap_logic.config.OPENROUTER_FREE_MODEL
    assert len(calls) == 2


def test_rate_limited_model_moves_to_tail_for_next_request(monkeypatch):
    ap_logic._MODEL_COOLDOWN_UNTIL.clear()
    monkeypatch.setattr(ap_logic.config, "AI_MODEL_COOLDOWN_SECONDS", 60)
    calls = []

    class RateLimited(Exception):
        status_code = 429

    async def create(**kwargs):
        calls.append(kwargs["model"])
        if len(calls) == 1:
            raise RateLimited("upstream rate limit")
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    try:
        run(ap_logic.chat_with_fallback([{"role": "user", "content": "first"}], models=[
            ap_logic.config.OPENROUTER_FREE_MODEL,
            ap_logic.config.OPENROUTER_FREE_MODEL_2,
        ]))
        run(ap_logic.chat_with_fallback([{"role": "user", "content": "second"}], models=[
            ap_logic.config.OPENROUTER_FREE_MODEL,
            ap_logic.config.OPENROUTER_FREE_MODEL_2,
        ]))

        assert calls == [
            ap_logic.config.OPENROUTER_FREE_MODEL,
            ap_logic.config.OPENROUTER_FREE_MODEL_2,
            ap_logic.config.OPENROUTER_FREE_MODEL_2,
        ]
    finally:
        ap_logic._MODEL_COOLDOWN_UNTIL.clear()


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
    ap_logic.config.OPENROUTER_ALLOW_PAID_FALLBACK = True
    route = ap_logic.select_model_route([
        {"role": "user", "content": "Сравни архитектуры и составь подробный план миграции."},
    ])
    free = [ap_logic.config.OPENROUTER_FREE_MODEL, ap_logic.config.OPENROUTER_FREE_MODEL_2, ap_logic.config.OPENROUTER_FREE_MODEL_3, ap_logic.config.OPENROUTER_FREE_MODEL_4, ap_logic.config.OPENROUTER_FREE_MODEL_5]
    assert route[:5] == free
    assert route[5] == ap_logic.config.OPENROUTER_REASONING_MODEL
    ap_logic.config.OPENROUTER_ALLOW_PAID_FALLBACK = False


def test_paid_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_ALLOW_PAID_FALLBACK", False)
    route = ap_logic.select_model_route([{"role": "user", "content": "сравни два варианта"}])
    assert route == [ap_logic.config.OPENROUTER_FREE_MODEL, ap_logic.config.OPENROUTER_FREE_MODEL_2, ap_logic.config.OPENROUTER_FREE_MODEL_3, ap_logic.config.OPENROUTER_FREE_MODEL_4, ap_logic.config.OPENROUTER_FREE_MODEL_5]


def test_paid_models_are_last_resort(monkeypatch):
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_ALLOW_PAID_FALLBACK", True)
    route = ap_logic.select_model_route([{"role": "user", "content": "Привет"}])
    free = [ap_logic.config.OPENROUTER_FREE_MODEL, ap_logic.config.OPENROUTER_FREE_MODEL_2, ap_logic.config.OPENROUTER_FREE_MODEL_3, ap_logic.config.OPENROUTER_FREE_MODEL_4, ap_logic.config.OPENROUTER_FREE_MODEL_5]
    assert route[:5] == free
    assert route[5] == ap_logic.config.OPENROUTER_MODEL


def test_simple_request_uses_fast_model_first():
    route = ap_logic.select_model_route([{"role": "user", "content": "Привет, как дела?"}])
    assert route[0] == ap_logic.config.OPENROUTER_FREE_MODEL


def test_visual_request_uses_free_vision_model_first():
    route = ap_logic.select_model_route([{
        "role": "user",
        "content": [
            {"type": "text", "text": "What is in this photo?"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}},
        ],
    }])
    assert route[0] == ap_logic.config.OPENROUTER_FREE_VISION_MODEL
    assert ap_logic.config.OPENROUTER_MODEL not in route[:2]


def test_long_system_prompt_does_not_force_reasoning_route():
    route = ap_logic.select_model_route([
        {"role": "system", "content": "memory " * 1000},
        {"role": "user", "content": "Привет"},
    ])
    assert route[0] == ap_logic.config.OPENROUTER_FREE_MODEL


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
