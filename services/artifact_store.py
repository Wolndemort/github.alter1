"""Short-lived, owner-scoped storage for reusable generated/edit results."""
from __future__ import annotations

import base64
import json
import logging
import secrets
from datetime import datetime, timezone

from config import config
from utils.redis_store import close_redis, create_redis

LOGGER = logging.getLogger(__name__)


def _key(artifact_id: str) -> str:
    return f"alter:artifact:{artifact_id}"


def _latest_key(user_id: int) -> str:
    return f"alter:artifact_latest:{int(user_id)}"


async def save_artifact(user_id: int, data: bytes, filename: str, media_type: str, *, kind: str, operation: str) -> str:
    artifact_id = secrets.token_urlsafe(12)
    value = {
        "id": artifact_id, "user_id": int(user_id), "filename": str(filename or "artifact")[:180],
        "media_type": str(media_type or "application/octet-stream")[:120], "kind": str(kind)[:32],
        "operation": str(operation)[:64], "created_at": datetime.now(timezone.utc).isoformat(),
        "data_base64": base64.b64encode(bytes(data)).decode("ascii"),
    }
    redis = create_redis()
    try:
        await redis.set(_key(artifact_id), json.dumps(value, ensure_ascii=False), ex=config.MEDIA_JOB_TTL_SECONDS)
        await redis.set(_latest_key(user_id), artifact_id, ex=config.MEDIA_JOB_TTL_SECONDS)
        await redis.lpush(f"alter:artifact_history:{int(user_id)}", artifact_id)
        await redis.ltrim(f"alter:artifact_history:{int(user_id)}", 0, 19)
    except Exception as exc:
        # Artifact reuse is an enhancement; a Redis outage must not turn a
        # successful provider result into a failed media request.
        LOGGER.warning("artifact registry unavailable: %s", str(exc)[:180])
        return ""
    finally:
        await close_redis(redis)
    return artifact_id


async def latest_artifact(user_id: int, *, kind: str | None = None) -> dict | None:
    """Return the newest live artifact owned by the user, optionally by kind."""
    redis = create_redis()
    try:
        latest_id = await redis.get(_latest_key(user_id))
        ids = ([latest_id] if latest_id else []) + await redis.lrange(f"alter:artifact_history:{int(user_id)}", 0, 19)
        seen = set()
        for artifact_id in ids:
            if artifact_id in seen:
                continue
            seen.add(artifact_id)
            raw = await redis.get(_key(str(artifact_id)))
            if not raw:
                continue
            try:
                value = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and int(value.get("user_id", -1)) == int(user_id) and (kind is None or value.get("kind") == kind):
                return value
        return None
    finally:
        await close_redis(redis)


async def get_artifact(user_id: int, artifact_id: str) -> dict | None:
    redis = create_redis()
    try:
        raw = await redis.get(_key(str(artifact_id or "")))
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) and int(value.get("user_id", -1)) == int(user_id) else None
    finally:
        await close_redis(redis)
