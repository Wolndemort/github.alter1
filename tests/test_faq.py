import asyncio

from aiohttp import web

from api.faq_routes import faq_route, faq_text_route, setup_faq_routes
from utils.faq import FAQ_TEXT, faq_html, faq_text


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


def test_faq_text_is_the_canonical_full_copy_for_first_party_clients():
    text = faq_text()
    assert "АКТУАЛЬНАЯ КАРТА ВОЗМОЖНОСТЕЙ" in text
    assert "64" in text and "artifact_id" in text and "\u0442\u0435\u043a\u0441\u0442\u043e\u0432\u044b\u043c \u0441\u043b\u043e\u0435\u043c" in text
    response = asyncio.run(faq_text_route(Request()))
    assert response.content_type == "text/plain"
    assert response.charset == "utf-8"
    assert response.text == text


def test_faq_text_route_is_registered_without_replacing_html_route():
    app = web.Application()
    setup_faq_routes(app)
    routes = {resource.canonical for resource in app.router.resources()}
    assert {"/api/v1/faq", "/api/v1/faq/text"} <= routes
