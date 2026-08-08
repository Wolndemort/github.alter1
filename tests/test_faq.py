import asyncio

from aiohttp import web

from api.faq_routes import faq_route, setup_faq_routes
from utils.faq import FAQ_TEXT, faq_html


class Request:
    pass


def test_faq_contains_all_major_capability_groups():
    for section in ("Память", "Поиск", "Погода", "Фото", "Голос", "Напоминания", "Calendar", "HTTP API", "лимит"):
        assert section.casefold() in FAQ_TEXT.casefold()
    assert "api.elevenlabs" not in FAQ_TEXT
    assert "fal.ai" not in FAQ_TEXT


def test_faq_is_black_white_html_and_route_is_registered():
    page = faq_html()
    assert "background:#050505" in page
    assert "FAQ" in page
    app = web.Application()
    setup_faq_routes(app)
    assert "/api/v1/faq" in {resource.canonical for resource in app.router.resources()}


def test_faq_route_returns_html():
    response = asyncio.run(faq_route(Request()))
    assert response.content_type == "text/html"
    assert response.charset == "utf-8"
