import asyncio
from types import SimpleNamespace

from pydantic import SecretStr

from services import yandex_maps


def test_geocode_uses_yandex_key_and_normalizes_response(monkeypatch):
    yandex_maps.config.YANDEX_MAPS_GEOCODER_API_KEY = SecretStr("test")

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


def test_map_operations_use_their_dedicated_keys(monkeypatch):
    for name in ("YANDEX_MAPS_ORG_API_KEY", "YANDEX_MAPS_ROUTE_API_KEY", "YANDEX_MAPS_DISTANCE_MATRIX_API_KEY"):
        setattr(yandex_maps.config, name, SecretStr("test"))

    class Response:
        status_code = 200
        def json(self): return {"features": [{"properties": {"name": "Cafe"}, "geometry": {"coordinates": [37.6, 55.7]}}]}
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr(yandex_maps.httpx, "AsyncClient", lambda **kwargs: Client())
    assert asyncio.run(yandex_maps.search_organizations("Cafe"))[0]["name"] == "Cafe"
    assert "features" in asyncio.run(yandex_maps.route("37.6,55.7", "37.7,55.8"))
    assert "features" in asyncio.run(yandex_maps.distance_matrix("37.6,55.7", "37.7,55.8"))
