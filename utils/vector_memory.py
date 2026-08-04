import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from data.models import MemoryChunk
from utils.ap_logic import client
from config import config

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
        logging.exception("Vector memory save failed")


async def recall(db: AsyncSession, user_id: int, text: str, limit=5) -> list[str]:
    try:
        vector = await embed(text)
        result = await db.execute(
            select(MemoryChunk.content)
            .where(MemoryChunk.user_id == user_id)
            .order_by(MemoryChunk.embedding.cosine_distance(vector))
            .limit(limit)
        )
        return list(result.scalars())
    except Exception:
        logging.exception("Vector memory search failed")
        return []
