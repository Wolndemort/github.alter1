"""Small safe image-search adapter for explicit 'send me a picture' requests."""
from __future__ import annotations

import aiohttp

from config import config
from utils.url_safety import validate_public_url


async def search_images(query: str, limit: int = 5) -> list[dict]:
    limit = max(1, min(limit, 5))
    if config.GOOGLE_CSE_API_KEY and config.GOOGLE_CSE_ID:
        try:
            async with aiohttp.ClientSession() as session:
                params = {"key": config.GOOGLE_CSE_API_KEY.get_secret_value(), "cx": config.GOOGLE_CSE_ID, "q": query, "searchType": "image", "num": limit, "safe": "active"}
                async with session.get("https://www.googleapis.com/customsearch/v1", params=params) as response:
                    if response.status == 200:
                        return [{"title": item.get("title", "Изображение"), "url": item.get("link", ""), "mime": item.get("mime", "")}
                                for item in (await response.json()).get("items", []) if item.get("link")]
        except Exception:
            pass
    # Wikimedia Commons is keyless and gives us a stable, openly licensed fallback.
    try:
        async with aiohttp.ClientSession() as session:
            params = {"action": "query", "generator": "search", "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": 1600, "format": "json"}
            async with session.get("https://commons.wikimedia.org/w/api.php", params=params) as response:
                pages = (await response.json()).get("query", {}).get("pages", {}) if response.status == 200 else {}
        return [{"title": item.get("title", "Изображение"), "url": (item.get("imageinfo") or [{}])[0].get("thumburl") or (item.get("imageinfo") or [{}])[0].get("url", ""), "mime": (item.get("imageinfo") or [{}])[0].get("mime", "")}
                for item in pages.values() if (item.get("imageinfo") or [{}])[0].get("url")]
    except Exception:
        return []


async def download_image(url: str, max_bytes: int = 20 * 1024 * 1024) -> tuple[bytes, str, str] | None:
    try:
        safe_url = validate_public_url(url)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(safe_url, allow_redirects=True) as response:
                mime = (response.headers.get("Content-Type") or "").split(";", 1)[0].casefold()
                if response.status != 200 or not mime.startswith("image/"):
                    return None
                data = await response.content.read(max_bytes + 1)
                if len(data) > max_bytes:
                    return None
                return data, mime, safe_url.rsplit("/", 1)[-1].split("?", 1)[0][:80] or "alter-image"
    except Exception:
        return None
