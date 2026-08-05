import asyncio
from types import SimpleNamespace

from utils import ap_logic, web_search, youtube_search
from utils.tasks import process_session
from data.models import Session, User
from utils import metrics


def run(coro):
    return asyncio.run(coro)


def test_openrouter_failure_returns_safe_reply(monkeypatch):
    async def fail(**kwargs):
        raise RuntimeError("provider down")
    monkeypatch.setattr(ap_logic.client.chat.completions, "create", fail)
    assert "не удалось получить" in run(ap_logic.generate_reply([])).lower()


def test_metrics_count_failures_and_snapshot(monkeypatch):
    metrics.reset()

    async def fail(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", fail)
    run(ap_logic.generate_reply([]))
    values = metrics.snapshot()
    assert values["ai.reply.failure"] == 1
    assert values["ai.model.failure"] >= 1


def test_youtube_non_200_returns_empty(monkeypatch):
    class Response:
        status = 503
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr(youtube_search.config, "YOUTUBE_API_KEY", SimpleNamespace(get_secret_value=lambda: "key"))
    monkeypatch.setattr(youtube_search.aiohttp, "ClientSession", lambda: Session())
    assert run(youtube_search.search_youtube("test")) == []


def test_youtube_malformed_items_are_ignored(monkeypatch):
    class Response:
        status = 200
        async def json(self): return {"items": [{"id": {}, "snippet": {}}]}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr(youtube_search.config, "YOUTUBE_API_KEY", SimpleNamespace(get_secret_value=lambda: "key"))
    monkeypatch.setattr(youtube_search.aiohttp, "ClientSession", lambda: Session())
    assert run(youtube_search.search_youtube("test")) == []


def test_web_search_returns_valid_results(monkeypatch):
    class Response:
        status = 200
        async def json(self):
            return {"results": [
                {"title": "Useful", "url": "https://example.com", "content": "Fact"},
                {"title": "Broken", "content": "No URL"},
            ]}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr(web_search.config, "TAVILY_API_KEY", SimpleNamespace(get_secret_value=lambda: "key"))
    monkeypatch.setattr(web_search.aiohttp, "ClientSession", lambda **kwargs: Session())
    result = run(web_search.search_web("test"))
    assert result == [{"title": "Useful", "url": "https://example.com", "content": "Fact"}]


def test_web_search_handles_api_error(monkeypatch):
    class Response:
        status = 500
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr(web_search.config, "TAVILY_API_KEY", SimpleNamespace(get_secret_value=lambda: "key"))
    monkeypatch.setattr(web_search.aiohttp, "ClientSession", lambda **kwargs: Session())
    assert run(web_search.search_web("test")) == []


def test_web_search_handles_network_exception(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            raise OSError("network down")

    monkeypatch.setattr(web_search.config, "TAVILY_API_KEY", SimpleNamespace(get_secret_value=lambda: "key"))
    monkeypatch.setattr(web_search.aiohttp, "ClientSession", lambda **kwargs: Session())
    assert run(web_search.search_web("test")) == []


def test_generate_reply_includes_search_context(monkeypatch):
    captured = {}
    async def fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
    monkeypatch.setattr(ap_logic.client.chat.completions, "create", fake_create)
    assert run(ap_logic.generate_reply([], search_results=[{"title": "Source", "url": "https://example.com", "content": "Important fact"}])) == "ok"
    assert any("Important fact" in message.get("content", "") for message in captured["messages"])


def test_process_session_persists_memory_and_marks_processed(monkeypatch):
    async def summarize(messages):
        return {"important_events": {"title": "Демо", "event_type": "career"}}
    monkeypatch.setattr("utils.tasks.summarize_session", summarize)
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    session = Session(raw_messages=[], user=user, is_processed=False)
    added = []
    class DB:
        def add(self, item): added.append(item)
        async def commit(self): pass
    assert run(process_session(session, DB())) is True
    assert session.is_processed is True
    assert user.memory["important_events"]["title"] == "Демо"
    assert added[0].title == "Демо"
