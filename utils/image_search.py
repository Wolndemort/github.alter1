"""Small safe image-search adapter for explicit 'send me a picture' requests."""
from __future__ import annotations

import html
import logging
import re
import asyncio

import aiohttp

from config import config
from utils.url_safety import validate_public_url


async def _yandex_images(query: str, limit: int) -> list[dict]:
    if not config.YANDEX_SEARCH_API_KEY:
        return []
    def run() -> list[dict]:
        from yandex_ai_studio_sdk import AIStudio
        sdk = AIStudio(folder_id=config.YANDEX_SEARCH_FOLDER_ID, auth=config.YANDEX_SEARCH_API_KEY.get_secret_value())
        search = sdk.search_api.image("SEARCH_TYPE_RU").configure(
            search_type="SEARCH_TYPE_RU", family_mode="FAMILY_MODE_MODERATE",
            fix_typo_mode="FIX_TYPO_MODE_ON", docs_on_page=max(10, limit),
            user_agent="Mozilla/5.0 ALTER/1.0",
        )
        result = search.run(query, format="parsed", page=0)
        return [{"title": "Изображение", "url": doc.url or "", "mime": doc.format or ""}
                for doc in result.docs if doc.url]
    try:
        return (await asyncio.to_thread(run))[:limit]
    except Exception:
        logging.exception("Yandex image search failed")
        return []


async def search_images(query: str, limit: int = 5) -> list[dict]:
    limit = max(1, min(limit, 5))
    yandex = await _yandex_images(query, limit)
    # Do not stop at Yandex: its result URLs can be preview pages or expire
    # before download. Keep them as candidates and continue to public fallbacks.
    if config.GOOGLE_CSE_API_KEY and config.GOOGLE_CSE_ID:
        try:
            async with aiohttp.ClientSession() as session:
                params = {"key": config.GOOGLE_CSE_API_KEY.get_secret_value(), "cx": config.GOOGLE_CSE_ID, "q": query, "searchType": "image", "num": limit, "safe": "active"}
            async with session.get("https://www.googleapis.com/customsearch/v1", params=params, headers={"User-Agent": "ALTER/1.0 (image search)"}) as response:
                    if response.status == 200:
                        return yandex + [{"title": item.get("title", "Изображение"), "url": item.get("link", ""), "mime": item.get("mime", "")}
                                         for item in (await response.json()).get("items", []) if item.get("link")]
        except Exception:
            pass
    # Wikimedia's REST search is keyless and is more reliable than the legacy API.
    try:
        # Commons has much better coverage for English medical terminology;
        # retry common Russian anatomy wording with an English equivalent.
        queries = [query]
        lowered = query.casefold()
        if "триггер" in lowered and "зон" in lowered:
            queries.append("trigger points anatomy")
        async with aiohttp.ClientSession() as session:
            for search_query in queries:
                params = {"q": search_query, "limit": limit}
                async with session.get("https://commons.wikimedia.org/w/rest.php/v1/search/page", params=params, headers={"User-Agent": "Mozilla/5.0 ALTER/1.0"}) as response:
                    pages = (await response.json()).get("pages", []) if response.status == 200 else []
                results = [{"title": item.get("title", "Изображение"), "url": (item.get("thumbnail") or {}).get("url", ""), "mime": (item.get("thumbnail") or {}).get("mimetype", "")}
                           for item in pages if (item.get("thumbnail") or {}).get("url")]
                if results:
                    return yandex + results
        return []
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
        return yandex + [{"title": "Изображение", "url": url, "mime": ""} for url in urls[:limit]]
    except Exception:
        return yandex


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
                # Search providers occasionally label an HTML/error body as an
                # image or return a browser-unfriendly WebP variant. Decode and
                # normalize it before sending it to web, mobile, and Telegram.
                try:
                    from io import BytesIO
                    from PIL import Image

                    with Image.open(BytesIO(data)) as image:
                        image.load()
                        normalized = BytesIO()
                        image.convert("RGB").save(normalized, format="JPEG", quality=92, optimize=True)
                    return normalized.getvalue(), "image/jpeg", "alter-image.jpg"
                except Exception:
                    return None
    except Exception:
        return None
