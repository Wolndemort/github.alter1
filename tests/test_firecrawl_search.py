import asyncio
from types import SimpleNamespace

from utils import web_search


def run(coro):
    return asyncio.run(coro)


def _key(value):
    return SimpleNamespace(get_secret_value=lambda: value)


def test_tavily_and_firecrawl_results_are_merged_and_deduplicated(monkeypatch):
    class Response:
        def __init__(self, data): self.status, self.data = 200, data
        async def json(self): return self.data
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def post(self, url, **kwargs):
            if "tavily" in url:
                return Response({"results": [{"title": "A", "url": "https://a.test", "content": "a"}]})
            return Response({"data": [
                {"title": "A duplicate", "url": "https://a.test", "markdown": "duplicate"},
                {"title": "B", "url": "https://b.test", "markdown": "b"},
            ]})

    monkeypatch.setattr(web_search.config, "TAVILY_API_KEY", _key("tavily-secret"))
    monkeypatch.setattr(web_search.config, "FIRECRAWL_API_KEY", _key("firecrawl-secret"))
    monkeypatch.setattr(web_search.aiohttp, "ClientSession", lambda **kwargs: Session())
    assert run(web_search.search_web("test", max_results=5)) == [
        {"title": "A", "url": "https://a.test", "content": "a"},
        {"title": "B", "url": "https://b.test", "content": "b"},
    ]


def test_firecrawl_is_used_when_tavily_is_not_configured(monkeypatch):
    class Response:
        status = 200
        async def json(self): return {"data": [{"title": "Result", "url": "https://x.test", "description": "x"}]}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()

    monkeypatch.setattr(web_search.config, "TAVILY_API_KEY", None)
    monkeypatch.setattr(web_search.config, "FIRECRAWL_API_KEY", _key("secret"))
    monkeypatch.setattr(web_search.aiohttp, "ClientSession", lambda **kwargs: Session())
    assert run(web_search.search_web("test"))[0]["url"] == "https://x.test"


def test_search_returns_empty_when_both_providers_fail(monkeypatch):
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def post(self, *args, **kwargs): raise OSError("offline")

    monkeypatch.setattr(web_search.config, "TAVILY_API_KEY", _key("tavily"))
    monkeypatch.setattr(web_search.config, "FIRECRAWL_API_KEY", _key("firecrawl"))
    monkeypatch.setattr(web_search.aiohttp, "ClientSession", lambda **kwargs: Session())
    assert run(web_search.search_web("test")) == []


def test_firecrawl_limit_is_per_request_result_count_not_provider_quota(monkeypatch):
    calls = []
    class Response:
        status = 200
        async def json(self): return {"data": [{"title": "Result", "url": "https://x.test"}]}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr(web_search.config, "TAVILY_API_KEY", None)
    monkeypatch.setattr(web_search.config, "FIRECRAWL_API_KEY", _key("secret"))
    monkeypatch.setattr(web_search.config, "FIRECRAWL_SEARCH_LIMIT", 10)
    monkeypatch.setattr(web_search.aiohttp, "ClientSession", lambda **kwargs: Session())
    run(web_search.search_web("test"))
    assert calls[0][1]["json"]["limit"] == 10
