from aiohttp import web

from utils.faq import faq_html, faq_text


async def faq_route(request: web.Request) -> web.Response:
    return web.Response(text=faq_html(), content_type="text/html", charset="utf-8")


async def faq_text_route(request: web.Request) -> web.Response:
    """Return the canonical FAQ as plain text for first-party clients."""
    return web.Response(text=faq_text(), content_type="text/plain", charset="utf-8")


def setup_faq_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/faq", faq_route)
    app.router.add_get("/api/v1/faq/text", faq_text_route)
