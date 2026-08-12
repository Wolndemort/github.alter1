import asyncio
from types import SimpleNamespace

from utils import ap_logic, metrics


def test_provider_usage_is_recorded_without_persisting_content(monkeypatch):
    class Usage:
        prompt_tokens = 12
        completion_tokens = 7

    async def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))], usage=Usage())

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_ALLOW_PAID_FALLBACK", True)
    metrics.reset()
    asyncio.run(ap_logic.chat_with_fallback([{"role": "user", "content": "secret"}]))
    snapshot = metrics.snapshot()
    assert snapshot["ai.tokens.prompt"] == 12
    assert snapshot["ai.tokens.completion"] == 7
