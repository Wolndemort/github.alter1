import asyncio
import time
from types import SimpleNamespace

from utils import ap_logic


def run(coro):
    return asyncio.run(coro)


def test_independent_tools_run_in_parallel(monkeypatch):
    calls = [
        SimpleNamespace(id="weather", function=SimpleNamespace(name="get_weather", arguments='{"city":"Москва"}')),
        SimpleNamespace(id="search", function=SimpleNamespace(name="web_search", arguments='{"query":"новости"}')),
    ]
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=calls))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Готово", tool_calls=[]))]),
    ]

    async def create(**kwargs):
        return responses.pop(0)

    async def tool(name, arguments):
        await asyncio.sleep(0.05)
        return {"name": name}

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    monkeypatch.setattr(ap_logic, "execute_tool", tool)
    started = time.perf_counter()
    result = run(ap_logic.chat_with_tools([{"role": "user", "content": "Сравни погоду и новости"}]))
    elapsed = time.perf_counter() - started

    assert result.choices[0].message.content == "Готово"
    assert elapsed < 0.09

