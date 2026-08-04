import asyncio
from types import SimpleNamespace

from data.models import MemoryChunk
from utils import vector_memory


def run(coro):
    return asyncio.run(coro)


def test_memory_chunk_contract():
    columns = MemoryChunk.__table__.columns
    assert {"user_id", "content", "embedding", "source", "created_at"} <= set(columns.keys())
    assert columns.embedding.type.dim == 1536


def test_embedding_uses_openrouter_model(monkeypatch):
    called = {}

    async def create(**kwargs):
        called.update(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1] * 1536)])

    monkeypatch.setattr(vector_memory.client.embeddings, "create", create)
    result = run(vector_memory.embed("hello"))
    assert len(result) == 1536
    assert called["model"] == "openai/text-embedding-3-small"


def test_remember_skips_short_text(monkeypatch):
    called = False

    async def embed(_):
        nonlocal called
        called = True
        return [0.0] * 1536

    class DB:
        def add(self, _):
            raise AssertionError("short text must not be stored")

    monkeypatch.setattr(vector_memory, "embed", embed)
    run(vector_memory.remember(DB(), 1, "short"))
    assert called is False


def test_remember_adds_embedded_chunk(monkeypatch):
    async def embed(_):
        return [0.2] * 1536

    added = []

    class DB:
        def add(self, item):
            added.append(item)

    monkeypatch.setattr(vector_memory, "embed", embed)
    run(vector_memory.remember(DB(), 42, "A sufficiently long memory fragment"))
    assert len(added) == 1
    assert isinstance(added[0], MemoryChunk)
    assert added[0].user_id == 42
    assert added[0].embedding == [0.2] * 1536


def test_recall_returns_empty_when_embedding_provider_fails(monkeypatch):
    async def fail(_):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(vector_memory, "embed", fail)
    assert run(vector_memory.recall(object(), 1, "question")) == []
