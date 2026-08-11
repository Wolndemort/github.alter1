import asyncio

from services.chat_service import _quality_gated_chunks
from utils.quality import PUBLIC_FALLBACK


async def _stream(*parts):
    for part in parts:
        yield part


def test_stream_quality_gate_replaces_reasoning_before_first_chunk():
    async def collect():
        return [chunk async for chunk in _quality_gated_chunks(_stream(
            "Okay, the user is feeling anxious. ",
            "Looking at the internal response mode, I need to follow the character guidelines.",
        ))]

    chunks = asyncio.run(collect())
    assert "".join(chunks) == PUBLIC_FALLBACK
    assert all("internal response mode" not in chunk.casefold() for chunk in chunks)
