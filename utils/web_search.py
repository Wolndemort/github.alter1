"""Provider-backed web search with Tavily + Firecrawl fallback/merging."""
from __future__ import annotations

import asyncio
import base64
import logging
import time
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp

from config import config
from utils.metrics import increment


_PROVIDER_FAILURES: dict[str, tuple[int, float]] = {}


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
        if any(marker in host for marker in (".gov", ".gov.ru", "yandex.ru", "google.com", "2gis.ru")):
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
                if config.FIRECRAWL_API_KEY:
                    add_provider("firecrawl", lambda: _firecrawl(session, query, min(limit, config.FIRECRAWL_SEARCH_LIMIT)))
                if config.GOOGLE_CSE_API_KEY and config.GOOGLE_CSE_ID:
                    add_provider("google", lambda: _google_cse(session, query, limit))
                if config.TWOGIS_API_KEY:
                    add_provider("2gis", lambda: _twogis(session, query, limit))
                provider_results: dict[str, list[dict]] = {}
                pending = set(tasks)
                deadline = asyncio.get_running_loop().time() + max(1, config.SEARCH_FAST_RETURN_SECONDS)
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
                    if len(current) >= max(1, config.SEARCH_MIN_RESULTS_BEFORE_FAST_RETURN):
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
