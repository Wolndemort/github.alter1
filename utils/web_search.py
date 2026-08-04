import aiohttp
import logging
from config import config


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    if not config.TAVILY_API_KEY:
        logging.warning("Web search skipped: TAVILY_API_KEY is not configured")
        return []
    payload = {"api_key": config.TAVILY_API_KEY.get_secret_value(), "query": query,
               "search_depth": "basic", "max_results": max_results, "include_answer": False}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post("https://api.tavily.com/search", json=payload) as response:
                if response.status != 200:
                    logging.warning("Tavily search failed with HTTP %s", response.status)
                    return []
                data = await response.json()
        return [item for item in data.get("results", []) if item.get("title") and item.get("url")]
    except Exception:
        logging.exception("Tavily search request failed")
        return []
