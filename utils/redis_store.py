"""Shared Redis primitives: FSM storage, short-lived cache and billing counters."""
import json
import secrets
from redis.asyncio import Redis

from config import config


def create_redis() -> Redis:
    return Redis.from_url(config.REDIS_URL, decode_responses=True)


async def close_redis(redis: Redis) -> None:
    await redis.aclose()


async def cache_get(redis: Redis, key: str) -> str | None:
    return await redis.get(f"alter:cache:{key}")


async def cache_set(redis: Redis, key: str, value: str, ttl: int | None = None) -> None:
    await redis.set(f"alter:cache:{key}", value, ex=ttl or config.REDIS_CACHE_TTL)


async def state_get(redis: Redis, namespace: str, user_id: int) -> dict | None:
    raw = await redis.get(f"alter:state:{namespace}:{user_id}")
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


async def state_set(redis: Redis, namespace: str, user_id: int, value: dict, ttl: int | None = None) -> None:
    await redis.set(f"alter:state:{namespace}:{user_id}", json.dumps(value, ensure_ascii=False), ex=ttl or config.SESSION_TIMEOUT)


async def state_delete(redis: Redis, namespace: str, user_id: int) -> None:
    await redis.delete(f"alter:state:{namespace}:{user_id}")


async def create_link_token(redis: Redis, user_id: int, ttl: int = 600) -> str:
    """Create a one-time Telegram linking token; the payload lives only in Redis."""
    token = secrets.token_urlsafe(32)
    await redis.set(f"alter:link:{token}", str(user_id), ex=ttl, nx=True)
    return token


async def consume_link_token(redis: Redis, token: str) -> int | None:
    """Consume a linking token atomically when Redis supports GETDEL."""
    raw = await redis.getdel(f"alter:link:{token}")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


async def charge_request(redis: Redis, user_id: int, limit: int) -> bool:
    """Atomically charge one daily request; returns False after the limit."""
    key = f"alter:billing:{user_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 86400)
    if count > limit:
        await redis.decr(key)
        return False
    return True


async def allow_request(redis: Redis, user_id: int, limit: int, window: int) -> bool:
    """Fixed-window Redis limiter. The counter is shared by all bot workers."""
    key = f"alter:spam:{user_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    if count > limit:
        return False
    return True
