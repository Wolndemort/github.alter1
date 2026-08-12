"""Small Yandex geocoding adapter; no map tiles or secrets are exposed."""
from __future__ import annotations

import httpx

from config import config


class YandexMapsError(RuntimeError):
    pass


def _api_key() -> str:
    key = getattr(config, "YANDEX_MAPS_API_KEY", None) or config.YANDEX_SEARCH_API_KEY
    if not key:
        raise YandexMapsError("Yandex Maps API key is not configured")
    return key.get_secret_value()


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
