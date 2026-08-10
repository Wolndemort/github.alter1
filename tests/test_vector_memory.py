import asyncio
from types import SimpleNamespace

from data.models import MemoryChunk
from utils import vector_memory


def run(coro):
    return asyncio.run(coro)


def test_memory_chunk_contract():
    columns = MemoryChunk.__table__.columns
    assert {"user_id", "content", "content_hash", "embedding", "source", "importance", "expires_at", "created_at"} <= set(columns.keys())
    assert columns.embedding.type.dim == 1536


def test_memory_lifecycle_migration_contract():
    from pathlib import Path
    migration = (Path(__file__).parents[1] / "alembic" / "versions" / "0014_memory_lifecycle.py").read_text(encoding="utf-8")
    assert 'revision = "0014_memory_lifecycle"' in migration
    assert 'down_revision = "0013_legal_consent"' in migration
    assert "content_hash" in migration
    assert "vector_cosine_ops" in migration


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
    assert len(added[0].content_hash) == 64
    assert added[0].expires_at is None


def test_recall_returns_empty_when_embedding_provider_fails(monkeypatch):
    async def fail(_):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(vector_memory, "embed", fail)
    assert run(vector_memory.recall(object(), 1, "question")) == []


def test_recall_applies_similarity_filter_and_small_default_limit(monkeypatch):
    async def fake_embed(_):
        return [0.1] * 1536

    captured = {}

    class Result:
        def scalars(self):
            return iter(["relevant memory"])

    class DB:
        async def execute(self, statement):
            captured["statement"] = str(statement)
            return Result()

    monkeypatch.setattr(vector_memory, "embed", fake_embed)
    assert run(vector_memory.recall(DB(), 1, "question")) == ["relevant memory"]
    assert "LIMIT" in captured["statement"].upper()
    assert "<=" in captured["statement"]


def test_remember_ignores_embedding_provider_failure(monkeypatch):
    async def fail(_):
        raise RuntimeError("embedding provider unavailable")

    class DB:
        def add(self, _):
            raise AssertionError("failed embedding must not add a chunk")

    monkeypatch.setattr(vector_memory, "embed", fail)
    run(vector_memory.remember(DB(), 1, "A sufficiently long memory fragment"))


def test_remember_skips_duplicate_content(monkeypatch):
    async def embed(_): raise AssertionError("duplicate must not be embedded")
    class Result:
        def scalar_one_or_none(self): return 99
    class DB:
        async def execute(self, statement): return Result()
        def add(self, _): raise AssertionError("duplicate must not be added")
    monkeypatch.setattr(vector_memory, "embed", embed)
    run(vector_memory.remember(DB(), 1, "A sufficiently long memory fragment"))


def test_purge_expired_never_deletes_permanent_memory():
    class Result:
        rowcount = 2
        def scalars(self): return self
        def all(self): return [1, 2]
    class DB:
        def __init__(self): self.calls = 0; self.committed = False
        async def execute(self, statement): self.calls += 1; return Result()
        async def commit(self): self.committed = True
    db = DB()
    assert run(vector_memory.purge_expired(db, limit=2)) == 0
    assert db.calls == 0 and not db.committed


def test_purge_expired_returns_zero_without_rows():
    class Result:
        def scalars(self): return self
        def all(self): return []
    class DB:
        async def execute(self, statement): return Result()
    assert run(vector_memory.purge_expired(DB())) == 0
