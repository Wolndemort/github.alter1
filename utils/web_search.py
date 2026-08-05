import aiohttp
import logging
from config import config
from utils.metrics import increment


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    if not config.TAVILY_API_KEY:
        logging.warning("Web search skipped: TAVILY_API_KEY is not configured")
        return []
    query = " ".join((query or "").split())[:500]
    if not query:
        return []
    payload = {
        "api_key": config.TAVILY_API_KEY.get_secret_value(),
        "query": query,
        # Advanced search gives the model several relevant passages instead
        # of only shallow page snippets, which is important for niche topics.
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post("https://api.tavily.com/search", json=payload) as response:
                if response.status != 200:
                    increment("search.web.failure", status=response.status)
                    logging.warning("Tavily search failed with HTTP %s", response.status)
                    return []
                data = await response.json()
        results = []
        seen_urls = set()
        for item in data.get("results", []):
            url = item.get("url")
            if not item.get("title") or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append({
                "title": item["title"],
                "url": url,
                "content": item.get("content", "")[:3000],
            })
        increment("search.web.success", results=len(results))
        return results
    except Exception:
        increment("search.web.failure", reason="exception")
        logging.exception("Tavily search request failed")
        return []
