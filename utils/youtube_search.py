import aiohttp
from config import config


async def search_youtube(query: str, max_results: int = 3) -> list[dict]:
    if not config.YOUTUBE_API_KEY:
        return []

    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "key": config.YOUTUBE_API_KEY.get_secret_value(),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.googleapis.com/youtube/v3/search", params=params) as response:
                if response.status != 200:
                    return []
                data = await response.json()
        return [
            {
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
            }
            for item in data.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
    except Exception:
        return []
