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
