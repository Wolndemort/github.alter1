"""Provider-backed web search with Tavily + Firecrawl fallback/merging."""
from __future__ import annotations

import asyncio
import base64
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp

from config import config
from utils.metrics import increment
from utils.intent import is_local_search_request
from utils.url_safety import validate_public_url


_PROVIDER_FAILURES: dict[str, tuple[int, float]] = {}


class _VisibleTextParser(HTMLParser):
    """Small dependency-free HTML to text extractor for source verification."""

    _SKIP = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.casefold() in self._SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.casefold() in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            value = html.unescape(data).strip()
            if value:
                self.parts.append(value)


def _page_text(body: bytes, charset: str | None = None) -> str:
    try:
        text = body.decode(charset or "utf-8", errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    parser = _VisibleTextParser()
    try:
        parser.feed(text)
    except Exception:
        return ""
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()[:6000]


async def _verify_source(session, item: dict) -> dict:
    """Fetch a top result and attach page text as stronger evidence."""
    value = dict(item)
    url = str(value.get("url") or "")
    try:
        safe_url = validate_public_url(url)
        async with session.get(
            safe_url,
            headers={"User-Agent": "ALTER/1.0 (+https://alterai.ru)"},
            allow_redirects=True,
        ) as response:
            if response.status != 200 or "text/html" not in str(response.headers.get("Content-Type", "")).casefold():
                return value
            validate_public_url(str(response.url))
            body = await response.content.read(250_000)
            text = _page_text(body, response.charset)
            if len(text) >= 160:
                value["content"] = (str(value.get("content") or "") + "\n\nПроверено по странице:\n" + text)[:9000]
                value["source_verified"] = True
    except Exception:
        logging.debug("Search source verification skipped for %s", url, exc_info=True)
    return value


async def _verify_sources(session, items: list[dict], limit: int = 2) -> list[dict]:
    """Verify only the first couple of sources to keep search bounded."""
    if not hasattr(session, "get"):
        return items
    selected = items[:max(0, limit)]
    if not selected:
        return items
    verified = await asyncio.gather(
        *(_verify_source(session, item) for item in selected),
        return_exceptions=True,
    )
    result = [item if isinstance(item, dict) else original for item, original in zip(verified, selected)]
    return result + items[len(selected):]


def _provider_is_available(name: str) -> bool:
    failures, last_failure = _PROVIDER_FAILURES.get(name, (0, 0.0))
    if failures < config.SEARCH_PROVIDER_FAILURE_THRESHOLD:
        return True
    if time.monotonic() - last_failure >= config.SEARCH_PROVIDER_COOLDOWN_SECONDS:
        _PROVIDER_FAILURES.pop(name, None)
        return True
    increment("search.web.provider_skipped", provider=name, reason="circuit_open")
    return False


def _record_provider_result(name: str, results: list[dict]) -> None:
    if results:
        _PROVIDER_FAILURES.pop(name, None)
        return
    failures, _ = _PROVIDER_FAILURES.get(name, (0, 0.0))
    _PROVIDER_FAILURES[name] = (failures + 1, time.monotonic())


async def _run_provider(name: str, operation_factory) -> list[dict]:
    if not _provider_is_available(name):
        return []
    try:
        results = await operation_factory()
    except asyncio.CancelledError:
        # A provider may cancel its own request; keep other providers alive.
        # Propagate cancellation only when our orchestrator cancelled the task.
        if asyncio.current_task() and asyncio.current_task().cancelling():
            raise
        results = []
    except Exception:
        results = []
    _record_provider_result(name, results if isinstance(results, list) else [])
    return results if isinstance(results, list) else []


def _reset_provider_breakers() -> None:
    """Reset state for deterministic tests and process-local recovery."""
    _PROVIDER_FAILURES.clear()


def _clean_query(query: str) -> str:
    return " ".join((query or "").split())[:500]


def _normalize(items, limit: int) -> list[dict]:
    results = []
    seen_urls = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link")
        title = item.get("title") or item.get("name")
        if not url or not title:
            continue
        canonical = _canonical_url(str(url))
        if canonical in seen_urls:
            continue
        seen_urls.add(canonical)
        content = item.get("content") or item.get("markdown") or item.get("description") or ""
        results.append({"title": str(title)[:500], "url": str(url), "content": str(content)[:3000]})
        if len(results) >= limit:
            break
    return results


def _canonical_url(url: str) -> str:
    """Deduplicate tracking variants without changing the displayed URL."""
    try:
        parsed = urlsplit(url.strip())
        query = [(key, value) for key, value in parse_qsl(parsed.query) if not key.casefold().startswith(("utm_", "yclid", "gclid"))]
        return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/"), urlencode(query), ""))
    except ValueError:
        return url.strip().casefold()


def _rank_results(items: list[dict], limit: int) -> list[dict]:
    """Prefer official and local-directory sources while keeping relevance order."""
    def score(item: dict) -> int:
        host = urlsplit(str(item.get("url") or "")).netloc.casefold()
        if any(marker in host for marker in (".gov", ".gov.ru", "yandex.ru", "google.com")):
            return 3
        if any(marker in host for marker in ("wikipedia.org", "youtube.com")):
            return 2
        return 1
    return [item for _, item in sorted(enumerate(items), key=lambda pair: (-score(pair[1]), pair[0]))[:limit]]


def _annotate_results(items: list[dict]) -> list[dict]:
    """Attach safe evidence metadata for the model's source comparison step."""
    annotated = []
    for item in items:
        value = dict(item)
        host = urlsplit(str(value.get("url") or "")).netloc.casefold()
        value["source_domain"] = host.removeprefix("www.")
        value["source_quality"] = "official" if any(marker in host for marker in (".gov", ".gov.ru")) else (
            "local_directory" if any(marker in host for marker in ("2gis.ru", "yandex.ru", "google.com")) else "web"
        )
        annotated.append(value)
    return annotated


async def _tavily(session, query: str, limit: int) -> list[dict]:
    if not config.TAVILY_API_KEY:
        return []
    payload = {
        "api_key": config.TAVILY_API_KEY.get_secret_value(),
        "query": query,
        "search_depth": "advanced",
        "max_results": limit,
        "include_answer": False,
    }
    try:
        async with session.post("https://api.tavily.com/search", json=payload) as response:
            if response.status != 200:
                increment("search.web.tavily.failure", status=response.status)
                logging.warning("Tavily search failed with HTTP %s", response.status)
                return []
            results = _normalize((await response.json()).get("results"), limit)
            increment("search.web.tavily.success", results=len(results))
            return results
    except Exception:
        increment("search.web.tavily.failure", reason="exception")
        logging.exception("Tavily search request failed")
        return []


async def _firecrawl(session, query: str, limit: int) -> list[dict]:
    if not config.FIRECRAWL_API_KEY:
        return []

    headers = {
        "Authorization": f"Bearer {config.FIRECRAWL_API_KEY.get_secret_value()}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "limit": limit, "scrapeOptions": {"formats": ["markdown"]}}
    try:
        async with session.post("https://api.firecrawl.dev/v1/search", headers=headers, json=payload) as response:
            if response.status != 200:
                increment("search.web.firecrawl.failure", status=response.status)
                logging.warning("Firecrawl search failed with HTTP %s", response.status)
                return []
            data = await response.json()
            items = data.get("data") or data.get("results") or []
            results = _normalize(items, limit)
            increment("search.web.firecrawl.success", results=len(results))
            return results
    except Exception:
        increment("search.web.firecrawl.failure", reason="exception")
        logging.exception("Firecrawl search request failed")
        return []


async def _google_cse(session, query: str, limit: int) -> list[dict]:
    if not config.GOOGLE_CSE_API_KEY or not config.GOOGLE_CSE_ID:
        return []
    params = {
        "key": config.GOOGLE_CSE_API_KEY.get_secret_value(),
        "cx": config.GOOGLE_CSE_ID,
        "q": query,
        "num": min(limit, 10),
    }
    try:
        async with session.get("https://www.googleapis.com/customsearch/v1", params=params) as response:
            if response.status != 200:
                increment("search.web.google.failure", status=response.status)
                return []
            data = await response.json()
            results = _normalize(data.get("items"), limit)
            increment("search.web.google.success", results=len(results))
            return results
    except Exception:
        increment("search.web.google.failure", reason="exception")
        logging.exception("Google CSE search failed")
        return []


async def _serper(session, query: str, limit: int) -> list[dict]:
    if not config.SERPER_API_KEY:
        return []
    try:
        async with session.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": config.SERPER_API_KEY.get_secret_value(), "Content-Type": "application/json"},
            json={"q": query, "num": min(limit, 10)},
        ) as response:
            if response.status != 200:
                increment("search.web.serper.failure", status=response.status)
                return []
            results = _normalize((await response.json()).get("organic"), limit)
            increment("search.web.serper.success", results=len(results))
            return results
    except Exception:
        increment("search.web.serper.failure", reason="exception")
        logging.exception("Serper search failed")
        return []


async def _yandex(session, query: str, limit: int) -> list[dict]:
    if not config.YANDEX_SEARCH_API_KEY:
        return []
    try:
        async with session.post(
            "https://searchapi.api.cloud.yandex.net/v2/web/search",
            headers={"Authorization": f"Api-Key {config.YANDEX_SEARCH_API_KEY.get_secret_value()}"},
            json={"folderId": config.YANDEX_SEARCH_FOLDER_ID, "query": {"searchType": "SEARCH_TYPE_RU", "queryText": query}, "sortSpec": {"sortMode": "SORT_MODE_BY_RELEVANCE"}, "groupSpec": {"groupMode": "GROUP_MODE_FLAT"}, "maxPassages": 2, "region": "225", "l10n": "LOCALIZATION_RU"},
        ) as response:
            if response.status != 200:
                increment("search.web.yandex.failure", status=response.status)
                return []
            data = await response.json()
            raw = data.get("results") or data.get("items") or data.get("webPages", {}).get("value", [])
            if not raw and data.get("rawData"):
                try:
                    document = ET.fromstring(base64.b64decode(data["rawData"]))
                    raw = []
                    for node in document.findall(".//doc"):
                        title_node = node.find("title")
                        url_node = node.find("url")
                        passage_nodes = node.findall("./passages/passage")
                        headline_node = node.find("headline")
                        raw.append({
                            "title": "".join(title_node.itertext()) if title_node is not None else "",
                            "url": url_node.text if url_node is not None else "",
                            "description": " ".join(
                                "".join(item.itertext()) for item in passage_nodes
                            ) or ("".join(headline_node.itertext()) if headline_node is not None else ""),
                        })
                except (ValueError, ET.ParseError):
                    raw = []
            results = _normalize(raw, limit)
            increment("search.web.yandex.success", results=len(results))
            return results
    except Exception:
        increment("search.web.yandex.failure", reason="exception")
        logging.exception("Yandex search failed")
        return []


async def _twogis(session, query: str, limit: int) -> list[dict]:
    if not config.TWOGIS_API_KEY:
        return []
    try:
        async with session.get(
            "https://catalog.api.2gis.com/3.0/items",
            params={"q": query, "page_size": min(limit, 10), "key": config.TWOGIS_API_KEY.get_secret_value()},
        ) as response:
            if response.status != 200:
                increment("search.web.2gis.failure", status=response.status)
                return []
            data = await response.json()
            raw = []
            for item in (data.get("result", {}).get("items", []) if isinstance(data, dict) else []):
                if not isinstance(item, dict):
                    continue
                raw.append({
                    "title": item.get("name") or item.get("full_name"),
                    "url": item.get("url") or (f"https://2gis.ru/firm/{item.get('id')}" if item.get("id") else None),
                    "description": item.get("address_name") or item.get("full_name") or "",
                })
            results = _normalize(raw, limit)
            increment("search.web.2gis.success", results=len(results))
            return results
    except Exception:
        increment("search.web.2gis.failure", reason="exception")
        logging.exception("2GIS search failed")
        return []
async def search_web(query: str, max_results: int = 10) -> list[dict]:
    query = _clean_query(query)
    if not query:
        return []
    limit = max(1, min(int(max_results), 10))
    if not config.TAVILY_API_KEY and not config.FIRECRAWL_API_KEY:
        if not any((config.GOOGLE_CSE_API_KEY and config.GOOGLE_CSE_ID, config.SERPER_API_KEY, config.YANDEX_SEARCH_API_KEY, config.TWOGIS_API_KEY)):
            logging.warning("Web search skipped: no search provider is configured")
            return []
    try:
        enhanced = any((config.GOOGLE_CSE_API_KEY and config.GOOGLE_CSE_ID, config.SERPER_API_KEY, config.YANDEX_SEARCH_API_KEY, config.TWOGIS_API_KEY))
        # Tavily is the primary path.  Firecrawl is a fallback only; waiting
        # for two providers in parallel allowed a stalled Firecrawl connection
        # to cancel an otherwise successful search stream.
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=config.SEARCH_PROVIDER_TIMEOUT_SECONDS)) as session:
            if enhanced:
                tasks: dict[asyncio.Task, str] = {}
                def add_provider(name: str, operation_factory) -> None:
                    task = asyncio.create_task(_run_provider(name, operation_factory))
                    tasks[task] = name
                if config.YANDEX_SEARCH_API_KEY:
                    add_provider("yandex", lambda: _yandex(session, query, limit))
                if config.SERPER_API_KEY:
                    add_provider("serper", lambda: _serper(session, query, limit))
                if config.TAVILY_API_KEY:
                    add_provider("tavily", lambda: _tavily(session, query, limit))
                # Firecrawl is a paid fallback, never a parallel provider when
                # the configured primary search stack (Yandex/Serper) exists.
                # Starting it here used credits even when its results were
                # discarded in favour of Yandex/Serper.
                if config.GOOGLE_CSE_API_KEY and config.GOOGLE_CSE_ID:
                    add_provider("google", lambda: _google_cse(session, query, limit))
                if config.TWOGIS_API_KEY and is_local_search_request(query):
                    add_provider("2gis", lambda: _twogis(session, query, limit))
                provider_results: dict[str, list[dict]] = {}
                pending = set(tasks)
                priority_names = {name for name in ("yandex", "serper") if name in tasks}
                # Directory results from 2GIS can arrive first, but must not
                # win the fast-return race over the configured web providers.
                deadline_seconds = config.SEARCH_PROVIDER_TIMEOUT_SECONDS if priority_names else config.SEARCH_FAST_RETURN_SECONDS
                deadline = asyncio.get_running_loop().time() + max(1, deadline_seconds)
                while pending:
                    remaining = max(0.0, deadline - asyncio.get_running_loop().time())
                    if not remaining:
                        break
                    done, pending = await asyncio.wait(pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        try:
                            provider_results[tasks[task]] = task.result()
                        except Exception:
                            provider_results[tasks[task]] = []
                    current = _normalize([item for provider in provider_results.values() for item in provider], limit)
                    priority_pending = any(tasks[task] in priority_names for task in pending)
                    if len(current) >= max(1, config.SEARCH_MIN_RESULTS_BEFORE_FAST_RETURN) and not priority_pending:
                        break
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                provider_order = ("yandex", "serper", "tavily", "firecrawl", "google", "2gis")
                ordered_items = [
                    item for provider in provider_order
                    for item in provider_results.get(provider, [])
                ]
                merged = _annotate_results(_rank_results(_normalize(ordered_items, limit), limit))
                merged = await _verify_sources(session, merged, limit=2)
                if merged:
                    increment("search.web.success", results=len(merged), providers=len(tasks))
                else:
                    increment("search.web.failure", reason="empty")
                return merged
            tavily = await _tavily(session, query, limit)
            firecrawl = []
            if not tavily:
                try:
                    firecrawl = await asyncio.wait_for(
                        _firecrawl(session, query, min(limit, config.FIRECRAWL_SEARCH_LIMIT)),
                        timeout=4,
                    )
                except asyncio.TimeoutError:
                    increment("search.web.firecrawl.failure", reason="timeout")
                    logging.warning("Firecrawl search timed out; returning empty fallback")
    except Exception:
        increment("search.web.failure", reason="session_exception")
        logging.exception("Web search session failed")
        return []

    providers = [item for item in (tavily, firecrawl) if isinstance(item, list)]
    merged = _normalize([item for provider in providers for item in provider], limit)
    if merged:
        increment("search.web.success", results=len(merged))
    else:
        increment("search.web.failure", reason="empty")
    return merged
