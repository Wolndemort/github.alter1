"""Authenticated download route for short-lived reusable artifacts."""
from __future__ import annotations

import base64

from aiohttp import web

from api.auth_routes import _bearer
from services.artifact_store import get_artifact


async def artifact_download_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    artifact = await get_artifact(user_id, request.match_info.get("artifact_id", ""))
    if not artifact:
        raise web.HTTPNotFound(text="artifact not found or expired")
    try:
        data = base64.b64decode(artifact.get("data_base64", ""), validate=True)
    except (ValueError, TypeError):
        raise web.HTTPNotFound(text="artifact not found or expired")
    response = web.Response(body=data, content_type=artifact.get("media_type") or "application/octet-stream")
    response.headers["Content-Disposition"] = f'attachment; filename="{artifact.get("filename", "artifact")}"'
    response.headers["X-ALTER-Artifact-ID"] = str(artifact.get("id", ""))
    return response


def setup_artifact_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/artifacts/{artifact_id}", artifact_download_route)
