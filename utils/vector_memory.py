import hashlib
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from data.models import MemoryChunk
from utils.ap_logic import client
from config import config
from utils.metrics import increment

EMBEDDING_MODEL = "openai/text-embedding-3-small"


async def embed(text: str) -> list[float]:
    response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text[:8000])
    return response.data[0].embedding


async def remember(db: AsyncSession, user_id: int, text: str, source="conversation") -> None:
    text = str(text or "").strip()
    if len(text) < 20:
        return
    try:
        content = text[:8000]
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if hasattr(db, "execute"):
            existing = await db.execute(select(MemoryChunk.id).where(
                MemoryChunk.user_id == user_id,
                MemoryChunk.content_hash == content_hash,
            ).limit(1))
            if existing.scalar_one_or_none() is not None:
                return
        ttl_days = 730 if source in {"explicit_memory", "important_event"} else 365
        db.add(MemoryChunk(
            user_id=user_id,
            content=content,
            content_hash=content_hash,
            embedding=await embed(content),
            source=source[:32],
            importance=1.0 if source in {"explicit_memory", "important_event"} else 0.5,
            expires_at=datetime.now(timezone.utc) + timedelta(days=ttl_days),
        ))
    except Exception:
        increment("memory.vector.save_failure")
        logging.exception("Vector memory save failed")


async def recall(
    db: AsyncSession,
    user_id: int,
    text: str,
    limit: int | None = None,
    max_distance: float | None = None,
) -> list[str]:
    try:
        vector = await embed(text)
        limit = limit or config.MEMORY_RECALL_LIMIT
        max_distance = config.MEMORY_RECALL_MAX_DISTANCE if max_distance is None else max_distance
        distance = MemoryChunk.embedding.cosine_distance(vector)
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(MemoryChunk.content)
            .where(
                MemoryChunk.user_id == user_id,
                distance <= max_distance,
                or_(MemoryChunk.expires_at.is_(None), MemoryChunk.expires_at > now),
            )
            .order_by(distance)
            .limit(limit)
        )
        values = list(result.scalars())
        increment("memory.vector.recall_success", results=len(values))
        return values
    except Exception:
        increment("memory.vector.recall_failure")
        logging.exception("Vector memory search failed")
        return []


async def purge_expired(db: AsyncSession, limit: int = 1000) -> int:
    """Delete expired episodic memories in bounded batches."""
    expired_ids = (await db.execute(
        select(MemoryChunk.id)
        .where(MemoryChunk.expires_at <= datetime.now(timezone.utc))
        .order_by(MemoryChunk.id)
        .limit(limit)
    )).scalars().all()
    if not expired_ids:
        return 0
    result = await db.execute(
        delete(MemoryChunk)
        .where(MemoryChunk.id.in_(expired_ids))
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return int(result.rowcount or 0)
