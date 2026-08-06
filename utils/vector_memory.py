import logging
from sqlalchemy import select
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
    if len(text.strip()) < 20:
        return
    try:
        db.add(MemoryChunk(user_id=user_id, content=text[:8000], embedding=await embed(text), source=source))
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
        result = await db.execute(
            select(MemoryChunk.content)
            .where(MemoryChunk.user_id == user_id, distance <= max_distance)
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
