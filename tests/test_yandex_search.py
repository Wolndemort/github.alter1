import asyncio

from pydantic import SecretStr

from utils import web_search


def run(coro):
    return asyncio.run(coro)


class Response:
    status = 200

    async def json(self):
        return {
            "results": [
                {"title": "Yandex result", "url": "https://example.ru/item", "description": "Описание"},
            ]
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class Session:
    def post(self, url, **kwargs):
        assert url == "https://searchapi.api.cloud.yandex.net/v2/web/search"
        assert kwargs["headers"]["Authorization"].startswith("Api-Key ")
        return Response()


def test_yandex_results_are_normalized(monkeypatch):
    monkeypatch.setattr(web_search.config, "YANDEX_SEARCH_API_KEY", SecretStr("test-yandex"))
    results = run(web_search._yandex(Session(), "купить ноутбук", 5))
    assert results == [{
        "title": "Yandex result",
        "url": "https://example.ru/item",
        "content": "Описание",
    }]


def test_empty_provider_opens_circuit_after_threshold(monkeypatch):
    monkeypatch.setattr(web_search.config, "SEARCH_PROVIDER_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr(web_search.config, "SEARCH_PROVIDER_COOLDOWN_SECONDS", 600)
    web_search._reset_provider_breakers()

    async def empty():
        return []

    assert run(web_search._run_provider("test", empty)) == []
    assert run(web_search._run_provider("test", empty)) == []
    called = False

    async def should_not_run():
        nonlocal called
        called = True
        return [{"title": "unexpected", "url": "https://example.ru"}]

    assert run(web_search._run_provider("test", should_not_run)) == []
    assert called is False
    web_search._reset_provider_breakers()
