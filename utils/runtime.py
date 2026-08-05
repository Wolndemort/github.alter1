"""Runtime dependency checks used before starting Telegram polling."""

import logging

from redis.asyncio import Redis
from sqlalchemy import text


async def check_dependencies(redis: Redis, engine) -> bool:
    """Return whether Redis and PostgreSQL are reachable, logging safe diagnostics."""
    healthy = True
    try:
        await redis.ping()
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
