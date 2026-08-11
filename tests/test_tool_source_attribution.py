import asyncio

from services import chat_service


async def _stream():
    yield "Current answer"


def test_tool_stream_adds_source_attribution(monkeypatch):
    monkeypatch.setattr(chat_service, "tool_trace", lambda: [{"tool": "web_search", "status": "ok"}])

    async def collect():
        return "".join([chunk async for chunk in chat_service._quality_gated_chunks(_stream(), tool_mode=True)])

    result = asyncio.run(collect())
    assert "Источник: подключённый инструмент ALTER." in result


def test_failed_tool_stream_is_explicit_about_missing_current_data(monkeypatch):
    monkeypatch.setattr(chat_service, "tool_trace", lambda: [{"tool": "web_search", "status": "error"}])

    async def collect():
        return "".join([chunk async for chunk in chat_service._quality_gated_chunks(_stream(), tool_mode=True)])

    result = asyncio.run(collect())
    assert "актуальные факты не подтверждены" in result
