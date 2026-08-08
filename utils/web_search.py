"""Provider-backed web search with Tavily + Firecrawl fallback/merging."""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from config import config
from utils.metrics import increment


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
        if not url or not title or url in seen_urls:
            continue
        seen_urls.add(url)
        content = item.get("content") or item.get("markdown") or item.get("description") or ""
        results.append({"title": str(title)[:500], "url": str(url), "content": str(content)[:3000]})
        if len(results) >= limit:
            break
    return results


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
            # Firecrawl has returned both {data: [...]} and {results: [...]} across API versions.
            items = data.get("data") or data.get("results") or []
            results = _normalize(items, limit)
            increment("search.web.firecrawl.success", results=len(results))
            return results
    except Exception:
        increment("search.web.firecrawl.failure", reason="exception")
        logging.exception("Firecrawl search request failed")
        return []


async def search_web(query: str, max_results: int = 10) -> list[dict]:
    query = _clean_query(query)
    if not query:
        return []
    limit = max(1, min(int(max_results), 10))
    if not config.TAVILY_API_KEY and not config.FIRECRAWL_API_KEY:
        logging.warning("Web search skipped: neither TAVILY_API_KEY nor FIRECRAWL_API_KEY is configured")
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            tavily, firecrawl = await asyncio.gather(
                _tavily(session, query, limit),
                _firecrawl(session, query, min(limit, config.FIRECRAWL_SEARCH_LIMIT)),
            )
    except Exception:
        increment("search.web.failure", reason="session_exception")
        logging.exception("Web search session failed")
        return []

    merged = _normalize(tavily + firecrawl, limit)
    if merged:
        increment("search.web.success", results=len(merged))
    else:
        increment("search.web.failure", reason="empty")
    return merged
