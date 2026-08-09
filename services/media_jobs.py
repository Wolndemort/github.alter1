"""Durable Redis queue and state for asynchronous media generation."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets
from datetime import datetime, timezone

from config import config
from services.media_generation import MediaGenerationError, generate_image, generate_video
from utils.redis_store import close_redis, create_redis

QUEUE_KEY = "alter:media_jobs"


def _key(job_id: str) -> str:
    return f"alter:media_job:{job_id}"


async def _save(redis, job_id: str, value: dict) -> None:
    await redis.set(_key(job_id), json.dumps(value, ensure_ascii=False), ex=config.MEDIA_JOB_TTL_SECONDS)


async def get_job(job_id: str) -> dict | None:
    redis = create_redis()
    try:
        raw = await redis.get(_key(job_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
    finally:
        await close_redis(redis)


async def history(user_id: int, limit: int = 20) -> list[dict]:
    redis = create_redis()
    try:
        ids = await redis.lrange(f"alter:media_history:{user_id}", 0, max(0, limit - 1))
        result = []
        for job_id in ids:
            raw = await redis.get(_key(job_id))
            if raw:
                try:
                    result.append(json.loads(raw))
                except (TypeError, json.JSONDecodeError):
                    continue
        return result
    finally:
        await close_redis(redis)


async def submit_job(user_id: int, kind: str, prompt: str, source: tuple[str, bytes] | None, options: dict) -> str:
    job_id = secrets.token_urlsafe(12)
    job = {"id": job_id, "user_id": user_id, "kind": kind, "status": "queued", "progress": 0, "created_at": datetime.now(timezone.utc).isoformat()}
    payload = {"id": job_id, "user_id": user_id, "kind": kind, "prompt": prompt, "source": source, "options": options}
    redis = create_redis()
    try:
        await _save(redis, job_id, job)
        await redis.rpush(QUEUE_KEY, json.dumps(payload))
    finally:
        await close_redis(redis)
    return job_id


async def cancel_job(job_id: str, user_id: int) -> bool:
    redis = create_redis()
    try:
        raw = await redis.get(_key(job_id))
        if not raw:
            return False
        job = json.loads(raw)
        if job.get("user_id") != user_id or job.get("status") in {"completed", "failed", "cancelled"}:
            return False
        job.update(status="cancelled", progress=0)
        await _save(redis, job_id, job)
        return True
    finally:
        await close_redis(redis)


async def _run(payload: dict, redis) -> None:
    job_id = payload["id"]
    raw = await redis.get(_key(job_id))
    if not raw:
        return
    job = json.loads(raw)
    if job.get("status") == "cancelled":
        return
    job.update(status="running", progress=10, started_at=datetime.now(timezone.utc).isoformat())
    await _save(redis, job_id, job)
    try:
        source = payload.get("source")
        if isinstance(source, list):
            source = (source[0], base64.b64decode(source[1]))
        artifact = await (generate_video(payload["prompt"], source, payload.get("options") or {}) if payload["kind"] == "video" else generate_image(payload["prompt"], source, payload.get("options") or {}))
        job.update(status="completed", progress=100, media_type=artifact.media_type, filename=artifact.filename, data_base64=base64.b64encode(artifact.data).decode("ascii"))
        history_key = f"alter:media_history:{payload['user_id']}"
        await redis.lpush(history_key, job_id)
        await redis.ltrim(history_key, 0, 19)
    except asyncio.CancelledError:
        job.update(status="cancelled", progress=0)
        raise
    except Exception as exc:
        job.update(status="failed", progress=0, error=str(exc)[:300])
        logging.exception("media job failed id=%s", job_id)
    await _save(redis, job_id, job)


async def media_job_worker() -> None:
    redis = create_redis()
    try:
        while True:
            item = await redis.blpop(QUEUE_KEY, timeout=0)
            if not item:
                continue
            try:
                payload = json.loads(item[1])
                await _run(payload, redis)
            except (TypeError, json.JSONDecodeError, KeyError):
                logging.exception("invalid media job payload")
    finally:
        await close_redis(redis)
