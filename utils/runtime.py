"""Runtime dependency checks used before starting Telegram polling."""

import logging
import time

from redis.asyncio import Redis
from sqlalchemy import text


async def check_dependencies(redis: Redis, engine) -> bool:
    """Return whether Redis and PostgreSQL are reachable, logging safe diagnostics."""
    healthy = True
    try:
        await redis.ping()
        probe = "alter:ready:write-probe"
        if all(callable(getattr(redis, name, None)) for name in ("set", "get", "delete")):
            await redis.set(probe, "1", ex=10)
            if await redis.get(probe) != "1":
                raise RuntimeError("Redis write/read probe failed")
            await redis.delete(probe)
    except Exception as exc:
        healthy = False
        logging.error("ALTER preflight: Redis недоступен (%s): %s", type(exc).__name__, str(exc)[:160])

    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception as exc:
        healthy = False
        logging.error("ALTER preflight: PostgreSQL недоступен (%s): %s", type(exc).__name__, str(exc)[:160])

    if healthy:
        logging.info("ALTER preflight: Redis и PostgreSQL доступны")
    return healthy


async def check_readiness(redis: Redis, engine) -> bool:
    """Readiness includes the asynchronous media worker, unlike startup checks."""
    if not await check_dependencies(redis, engine):
        return False
    heartbeat = await redis.get("alter:media_worker:heartbeat")
    try:
        return float(heartbeat or 0) >= time.time() - 45
    except (TypeError, ValueError):
        return False
