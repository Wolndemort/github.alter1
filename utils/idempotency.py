"""Small Redis-backed idempotency guard for chargeable operations."""
from __future__ import annotations

import hashlib
import re


TTL_SECONDS = 15 * 60


def normalize_key(value: str | None) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    value = re.sub(r"[^A-Za-z0-9._:-]", "", value)[:160]
    return value or None


def redis_key(user_id: int, route: str, key: str) -> str:
    digest = hashlib.sha256(f"{user_id}:{route}:{key}".encode()).hexdigest()
    return f"alter:idempotency:{digest}"


async def acquire(redis, user_id: int, route: str, key: str | None) -> str | None:
    """Return the Redis key when acquired; return None for duplicate requests."""
    normalized = normalize_key(key)
    if not normalized:
        return None
    storage_key = redis_key(user_id, route, normalized)
    acquired = await redis.set(storage_key, "1", ex=TTL_SECONDS, nx=True)
    return storage_key if acquired else ""


async def release(redis, storage_key: str | None) -> None:
    if storage_key:
        await redis.delete(storage_key)
