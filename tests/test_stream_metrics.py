import asyncio
from types import SimpleNamespace

from utils import ap_logic, metrics


def test_stream_records_first_token_and_completion(monkeypatch):
    class Stream:
        def __aiter__(self): return self
        async def __anext__(self):
            if getattr(self, "sent", False): raise StopAsyncIteration
            self.sent = True
            return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))])

    async def create(**kwargs): return Stream()
    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    metrics.reset()
    async def run():
        return [part async for part in ap_logic.stream_text_reply([{"role": "user", "content": "Привет"}], max_tokens=20)]
    assert asyncio.run(run()) == ["ok"]
    snapshot = metrics.snapshot()
    assert snapshot["ai.reply.first_token"] == 1
    assert snapshot["ai.reply.stream_completed"] == 1
