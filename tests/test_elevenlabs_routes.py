import base64

import pytest
from aiohttp import web

from api import elevenlabs_routes as routes


class Field:
    def __init__(self, name, text_value="", data=b"", filename=None):
        self.name = name
        self.filename = filename
        self._text_value = text_value
        self._data = data

    async def text(self):
        return self._text_value

    async def read(self, decode=False):
        return self._data


class Reader:
    def __init__(self, *fields):
        self.fields = iter(fields)

    async def next(self):
        return next(self.fields, None)


class Request:
    content_type = "multipart/form-data"

    def __init__(self, *fields):
        self.reader = Reader(*fields)

    async def multipart(self):
        return self.reader


@pytest.mark.asyncio
async def test_process_audio_requires_file_for_mix(monkeypatch):
    monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    monkeypatch.setattr(routes, "_allowed", lambda user_id: _true())
    with pytest.raises(web.HTTPBadRequest) as error:
        await routes.process_audio_route(Request(Field("prompt", "Наложи дождь на мое голосовое")))
    assert error.value.text == "audio file required for this action"


@pytest.mark.asyncio
async def test_process_audio_returns_base64_result(monkeypatch):
    monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    monkeypatch.setattr(routes, "_allowed", lambda user_id: _true())
    monkeypatch.setattr(routes, "charge_user_id_credits", lambda *args: _true())
    monkeypatch.setattr(routes, "create_redis", lambda: object())
    monkeypatch.setattr(routes, "close_redis", lambda redis: _true())

    async def fake_process(prompt, data, filename):
        assert "дождя" in prompt and data == b"voice"
        return "Готово", b"mp3"

    monkeypatch.setattr(routes, "process_audio_action", fake_process)
    response = await routes.process_audio_route(
        Request(Field("prompt", "Создай звук дождя"), Field("file", data=b"voice", filename="voice.m4a"))
    )
    assert response.status == 200
    assert base64.b64encode(b"mp3").decode() in response.text


async def _true():
    return True
