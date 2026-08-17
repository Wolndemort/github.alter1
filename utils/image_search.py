"""Small safe image-search adapter for explicit 'send me a picture' requests."""
from __future__ import annotations

import html
import re

import aiohttp

from config import config
from utils.url_safety import validate_public_url


async def search_images(query: str, limit: int = 5) -> list[dict]:
    limit = max(1, min(limit, 5))
    if config.GOOGLE_CSE_API_KEY and config.GOOGLE_CSE_ID:
        try:
            async with aiohttp.ClientSession() as session:
                params = {"key": config.GOOGLE_CSE_API_KEY.get_secret_value(), "cx": config.GOOGLE_CSE_ID, "q": query, "searchType": "image", "num": limit, "safe": "active"}
            async with session.get("https://www.googleapis.com/customsearch/v1", params=params, headers={"User-Agent": "ALTER/1.0 (image search)"}) as response:
                    if response.status == 200:
                        return [{"title": item.get("title", "Изображение"), "url": item.get("link", ""), "mime": item.get("mime", "")}
                                for item in (await response.json()).get("items", []) if item.get("link")]
        except Exception:
            pass
    # Wikimedia's REST search is keyless and is more reliable than the legacy API.
    try:
        async with aiohttp.ClientSession() as session:
            params = {"q": query, "limit": limit}
            async with session.get("https://commons.wikimedia.org/w/rest.php/v1/search/page", params=params, headers={"User-Agent": "Mozilla/5.0 ALTER/1.0"}) as response:
                pages = (await response.json()).get("pages", []) if response.status == 200 else []
        return [{"title": item.get("title", "Изображение"), "url": (item.get("thumbnail") or {}).get("url", ""), "mime": (item.get("thumbnail") or {}).get("mimetype", "")}
                for item in pages if (item.get("thumbnail") or {}).get("url")]
    except Exception:
        pass
    # Last-resort public search page fallback when API providers are absent or blocked.
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.google.com/search", params={"tbm": "isch", "q": query}, headers={"User-Agent": "Mozilla/5.0"}) as response:
                page = await response.text() if response.status == 200 else ""
        urls = []
        for raw in re.findall(r"https?://[^\"'\\ ]+", html.unescape(page)):
            url = raw.replace("\\u003d", "=").replace("\\u0026", "&")
            if any(ext in url.casefold() for ext in (".jpg", ".jpeg", ".png", ".webp")) and "google.com" not in url:
                if url not in urls:
                    urls.append(url)
        return [{"title": "Изображение", "url": url, "mime": ""} for url in urls[:limit]]
    except Exception:
        return []


async def download_image(url: str, max_bytes: int = 20 * 1024 * 1024) -> tuple[bytes, str, str] | None:
    try:
        safe_url = validate_public_url(url)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), headers={"User-Agent": "ALTER/1.0 (media fetch)"}) as session:
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
