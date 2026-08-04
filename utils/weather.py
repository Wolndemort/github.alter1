from urllib.parse import quote
import re
import aiohttp


def parse_weather_city(text: str) -> str:
    """Извлекает город из естественной русской просьбы о погоде."""
    value = re.sub(r"^/weather(?:@\w+)?\s*", "", (text or "").strip(), flags=re.IGNORECASE)
    value = re.sub(r"\b(какая|покажи|узнай|скажи|мне|пожалуйста|будет|сейчас|завтра|сегодня|погода|температура|прогноз|дождь|снег|в|во|для|на)\b", " ", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip(" ,.!?") or "Москва"


def is_weather_request(text: str) -> bool:
    value = (text or "").casefold()
    return value.startswith("/weather") or bool(re.search(r"\b(погода|прогноз|температур[аыуеой]?|дождь|снег)\b", value))


async def get_weather(city: str) -> str | None:
    city = city.strip() or "Москва"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://wttr.in/{quote(city)}", params={"format": "j1"}, headers={"User-Agent": "ALTER bot"}, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                data = await response.json()
        current = data["current_condition"][0]
        desc = current.get("lang_ru", current.get("weatherDesc"))[0]["value"]
        return f"🌤️ Погода в {city}: {desc}. Температура {current['temp_C']}°C, ощущается как {current['FeelsLikeC']}°C, влажность {current['humidity']}%."
    except Exception:
        return None
