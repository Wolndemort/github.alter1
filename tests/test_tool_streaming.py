import asyncio
from types import SimpleNamespace

from utils import ap_logic


def run(coro):
    return asyncio.run(coro)


def test_tool_streamer_executes_tools_then_streams_final_answer(monkeypatch):
    call = SimpleNamespace(id="call-1", function=SimpleNamespace(name="web_search", arguments='{"query":"ALTER"}'))
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[call]))]),
    ]
    async def create(**kwargs):
        if kwargs.get("stream"):
            class Stream:
                def __aiter__(self): return self
                async def __anext__(self):
                    if getattr(self, "done", False): raise StopAsyncIteration
                    self.done = True
                    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="финал"))])
            return Stream()
        return responses.pop(0)
    async def search(query): return [{"title": query}]
    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    monkeypatch.setattr(ap_logic, "execute_tool", search)
    assert run(collect(ap_logic.stream_chat_with_tools([{"role": "user", "content": "Найди ALTER"}]))) == ["финал"]


async def collect(iterator):
    return [item async for item in iterator]
