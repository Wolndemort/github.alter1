from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import web

from api import youtube_routes
from data.models import User


@pytest.fixture(autouse=True)
def paid_access(monkeypatch):
    monkeypatch.setattr(youtube_routes, "has_active_subscription", lambda user: True)
    async def allow_charge(user_id, cost): return None
    monkeypatch.setattr(youtube_routes, "_charge_youtube", allow_charge)


class Request:
    def __init__(self, payload): self.payload = payload
    async def json(self): return self.payload


class Db:
    def __init__(self, user): self.user = user
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def get(self, model, user_id): return self.user


@pytest.mark.asyncio
async def test_youtube_search_route_returns_results(monkeypatch):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    monkeypatch.setattr(youtube_routes, "_bearer", lambda request: 7)
    monkeypatch.setattr(youtube_routes, "async_session", lambda: Db(user))
    async def search(query, max_results): return [{"title": "Song", "channel": "Artist", "url": "https://youtube.com/watch?v=1"}]
    monkeypatch.setattr(youtube_routes, "search_youtube", search)
    response = await youtube_routes.youtube_search_route(Request({"query": "song"}))
    assert response.status == 200 and "Song" in response.text


@pytest.mark.asyncio
async def test_youtube_routes_validate_query_and_url(monkeypatch):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    monkeypatch.setattr(youtube_routes, "_bearer", lambda request: 7)
    monkeypatch.setattr(youtube_routes, "async_session", lambda: Db(user))
    with pytest.raises(web.HTTPBadRequest): await youtube_routes.youtube_search_route(Request({"query": ""}))
    with pytest.raises(web.HTTPBadRequest): await youtube_routes.youtube_audio_route(Request({"url": "https://evil.example/file"}))


@pytest.mark.asyncio
async def test_youtube_audio_returns_file_and_cleans_temp(monkeypatch, tmp_path):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    audio = tmp_path / "audio.mp3"; audio.write_bytes(b"mp3")
    monkeypatch.setattr(youtube_routes, "_bearer", lambda request: 7)
    monkeypatch.setattr(youtube_routes, "async_session", lambda: Db(user))
    async def download(url): return audio, "Song"
    removed = []
    monkeypatch.setattr(youtube_routes, "download_audio", download)
    monkeypatch.setattr(youtube_routes, "remove_audio", lambda path: removed.append(path))
    response = await youtube_routes.youtube_audio_route(Request({"url": "https://youtube.com/watch?v=1"}))
    assert response.status == 200 and response.body == b"mp3" and removed == [audio]
