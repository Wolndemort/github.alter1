import asyncio
from types import SimpleNamespace

from pydantic import SecretStr

from services import yandex_maps


def test_geocode_uses_yandex_key_and_normalizes_response(monkeypatch):
    yandex_maps.config.YANDEX_SEARCH_API_KEY = SecretStr("test")

    class Response:
        status_code = 200
        def json(self):
            return {"response": {"GeoObjectCollection": {"featureMember": [{"GeoObject": {"name": "Cafe", "Point": {"pos": "37.6 55.7"}}}]}}}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, *args, **kwargs): return Response()

    monkeypatch.setattr(yandex_maps.httpx, "AsyncClient", lambda **kwargs: Client())
    result = asyncio.run(yandex_maps.geocode("Cafe"))
    assert result[0]["name"] == "Cafe"
    assert result[0]["point"] == "37.6 55.7"
