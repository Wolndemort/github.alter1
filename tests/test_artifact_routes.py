import asyncio
import base64

from api import artifact_routes


class Request:
    headers = {"Authorization": "Bearer token"}
    match_info = {"artifact_id": "artifact-1"}


def test_artifact_download_is_owner_scoped_and_returns_binary(monkeypatch):
    async def fake_get(user_id, artifact_id):
        assert user_id == 7
        assert artifact_id == "artifact-1"
        return {"id": artifact_id, "user_id": 7, "filename": "alter.txt", "media_type": "text/plain", "data_base64": base64.b64encode(b"ready").decode()}

    monkeypatch.setattr(artifact_routes, "_bearer", lambda request: 7)
    monkeypatch.setattr(artifact_routes, "get_artifact", fake_get)
    response = asyncio.run(artifact_routes.artifact_download_route(Request()))
    assert response.status == 200
    assert response.body == b"ready"
    assert response.headers["X-ALTER-Artifact-ID"] == "artifact-1"
