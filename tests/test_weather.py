import asyncio

from utils import weather


def run(coro):
    return asyncio.run(coro)


class FakeResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self, **kwargs):
        assert kwargs == {"content_type": None}
        return {"current_condition": [{
            "lang_ru": [{"value": "ясно"}],
            "temp_C": "24",
            "FeelsLikeC": "25",
            "humidity": "40",
        }]}


class FakeSession:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def get(self, *args, **kwargs):
        return FakeResponse()


def test_weather_accepts_wttr_json_with_text_plain_content_type(monkeypatch):
    monkeypatch.setattr(weather.aiohttp, "ClientSession", FakeSession)
    result = run(weather.get_weather("Москва"))
    assert "24" in result
    assert "Москва" in result


def test_weather_request_helpers_handle_natural_language():
    assert weather.is_weather_request("какая погода в Москве")
    assert weather.parse_weather_city("погода в Москве") == "Москве"
    assert weather.parse_weather_city("Да, прогноз в Майкопе") == "Майкопе"
    assert weather.parse_weather_city("/weather Санкт-Петербург") == "Санкт-Петербург"
