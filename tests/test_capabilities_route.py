import asyncio

from aiohttp import web

from api.capabilities_routes import capabilities_route, setup_capabilities_routes


class Request:
    pass


def test_capabilities_route_is_registered_and_shared_payload_is_rendered():
    app = web.Application()
    setup_capabilities_routes(app)
    assert "/api/v1/capabilities" in {resource.canonical for resource in app.router.resources()}
    response = asyncio.run(capabilities_route(Request()))
    assert response.status == 200
    assert "reply" in response.text
    assert "documents" in response.text
    assert "document_edit_export" in response.text
