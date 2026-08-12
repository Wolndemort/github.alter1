"""Small Yandex geocoding adapter; no map tiles or secrets are exposed."""
from __future__ import annotations

import httpx

from config import config


class YandexMapsError(RuntimeError):
    pass


def _api_key() -> str:
    key = getattr(config, "YANDEX_MAPS_GEOCODER_API_KEY", None) or getattr(config, "YANDEX_MAPS_API_KEY", None) or config.YANDEX_SEARCH_API_KEY
    if not key:
        raise YandexMapsError("Yandex Maps API key is not configured")
    return key.get_secret_value()


async def _get(url: str, key_name: str, params: dict) -> dict:
    key = getattr(config, key_name, None)
    if not key:
        raise YandexMapsError(f"{key_name} is not configured")
    params = {**params, "apikey": key.get_secret_value()}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
        if response.status_code >= 400:
            raise YandexMapsError(f"Yandex Maps request failed: {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise YandexMapsError("Yandex Maps returned invalid data")
        return payload
    except YandexMapsError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise YandexMapsError("Yandex Maps is temporarily unavailable") from exc


async def geocode(query: str, *, results: int = 5) -> list[dict]:
    query = str(query or "").strip()
    if not query:
        raise YandexMapsError("address or place is required")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                "https://geocode-maps.yandex.ru/1.x/",
                params={"apikey": _api_key(), "geocode": query[:300], "format": "json", "results": max(1, min(results, 10))},
            )
        if response.status_code >= 400:
            raise YandexMapsError("Yandex Geocoder request failed")
        payload = response.json()
        members = payload.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
        return [
            {
                "name": item.get("GeoObject", {}).get("name", ""),
                "description": item.get("GeoObject", {}).get("description", ""),
                "uri": item.get("GeoObject", {}).get("uri", ""),
                "point": item.get("GeoObject", {}).get("Point", {}).get("pos", ""),
            }
            for item in members[:results]
            if isinstance(item, dict)
        ]
    except YandexMapsError:
        raise
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise YandexMapsError("Yandex Geocoder is temporarily unavailable") from exc


async def search_organizations(query: str, *, ll: str | None = None, results: int = 5) -> list[dict]:
    params = {"text": str(query or "").strip()[:300], "lang": "ru_RU", "type": "biz", "results": max(1, min(results, 10))}
    if ll:
        params["ll"] = ll
    payload = await _get("https://search-maps.yandex.ru/v1/", "YANDEX_MAPS_ORG_API_KEY", params)
    return [
        {"name": item.get("properties", {}).get("name", ""), "description": item.get("properties", {}).get("description", ""), "uri": item.get("properties", {}).get("CompanyMetaData", {}).get("url", ""), "point": item.get("geometry", {}).get("coordinates", [])}
        for item in payload.get("features", [])[:results] if isinstance(item, dict)
    ]


async def route(origin: str, destination: str, *, mode: str = "driving") -> dict:
    return await _get("https://api.routing.yandex.net/v2/route", "YANDEX_MAPS_ROUTE_API_KEY", {"waypoints": f"{origin}|{destination}", "mode": mode})


async def distance_matrix(origins: str, destinations: str, *, mode: str = "driving") -> dict:
    return await _get("https://api.routing.yandex.net/v2/distancematrix", "YANDEX_MAPS_DISTANCE_MATRIX_API_KEY", {"origins": origins, "destinations": destinations, "mode": mode})
