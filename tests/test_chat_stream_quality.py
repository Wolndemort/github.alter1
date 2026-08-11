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


def test_ordinary_stream_releases_safe_prefix_before_completion():
    async def collect():
        return [chunk async for chunk in _quality_gated_chunks(
            _stream("x" * 220, " финал"), early_stream=True
        )]

    chunks = asyncio.run(collect())
    assert "".join(chunks) == "x" * 220 + " финал"
    assert len(chunks) >= 3


def test_early_stream_does_not_release_internal_marker_in_prefix():
    async def collect():
        return [chunk async for chunk in _quality_gated_chunks(
            _stream("x" * 100, " internal response mode: hidden"), early_stream=True
        )]

    chunks = asyncio.run(collect())
    assert "internal response mode" not in "".join(chunks).casefold()
