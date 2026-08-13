"""Shared capability inventory endpoint used by all first-party clients."""
from aiohttp import web

from utils.capabilities import capabilities_reply
from utils.capability_catalog import capability_payload


async def capabilities_route(request: web.Request) -> web.Response:
    del request
    payload = capability_payload()
    payload["reply"] = capabilities_reply()
    return web.json_response(payload)


def setup_capabilities_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/capabilities", capabilities_route)
