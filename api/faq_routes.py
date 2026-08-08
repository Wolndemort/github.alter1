from aiohttp import web

from utils.faq import faq_html


async def faq_route(request: web.Request) -> web.Response:
    return web.Response(text=faq_html(), content_type="text/html", charset="utf-8")


def setup_faq_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/faq", faq_route)
