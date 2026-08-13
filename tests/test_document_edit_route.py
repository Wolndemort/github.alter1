import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from api import chat_routes
from data.models import User


class Field:
    def __init__(self, name, text_value="", data=b"", filename=None):
        self.name = name
        self.filename = filename
        self.headers = {"Content-Type": "text/plain"}
        self._text_value = text_value
        self._data = data

    async def text(self):
        return self._text_value

    async def read(self, decode=False):
        return self._data


class Reader:
    def __init__(self, *fields):
        self.fields = iter(fields)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.fields)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class Request:
    content_type = "multipart/form-data"

    def __init__(self, *fields):
        self.reader = Reader(*fields)

    async def multipart(self):
        return self.reader


class Db:
    def __init__(self, user):
        self.user = user

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, model, user_id):
        return self.user if user_id == self.user.id else None

    async def execute(self, query):
        return SimpleNamespace(scalar_one_or_none=lambda: None)


@pytest.mark.asyncio
async def test_document_edit_route_reuses_latest_artifact_and_normalizes_natural_instruction(monkeypatch):
    user = User(id=42, first_name="Test", memory={}, tech_stack={})
    user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    previous = {
        "filename": "notes.txt",
        "media_type": "text/plain",
        "data_base64": base64.b64encode(b"ready status").decode(),
    }
    edited = SimpleNamespace(data=b"final status", filename="notes.txt", media_type="text/plain")

    monkeypatch.setattr(chat_routes, "_bearer", lambda request: 42)
    monkeypatch.setattr(chat_routes, "async_session", lambda: Db(user))
    monkeypatch.setattr(chat_routes, "latest_artifact", lambda *args, **kwargs: _async_value(previous))
    monkeypatch.setattr(chat_routes, "edit_document", lambda filename, data, instruction, media_type: _assert_edit(filename, data, instruction, media_type, edited))
    monkeypatch.setattr(chat_routes, "save_artifact", lambda *args, **kwargs: _async_value("artifact-final"))
    monkeypatch.setattr(chat_routes, "has_owner_access", lambda *args, **kwargs: True)

    response = await chat_routes.document_edit_route(
        Request(Field("instruction", "\u0438\u0437\u043c\u0435\u043d\u0438 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 \u0441\u043e\u0437\u0434\u0430\u043d\u043d\u044b\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442: ready status => final status"))
    )

    assert response.status == 200
    assert response.body == b"final status"
    assert response.headers["X-ALTER-Artifact-ID"] == "artifact-final"


async def _async_value(value):
    return value


def _assert_edit(filename, data, instruction, media_type, edited):
    assert filename == "notes.txt"
    assert data == b"ready status"
    assert instruction == "ready status => final status"
    assert media_type == "text/plain"
    return edited
