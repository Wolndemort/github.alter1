"""Add vector memory deduplication and lifecycle metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0014_memory_lifecycle"
down_revision = "0013_legal_consent"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("memory_chunks", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("memory_chunks", sa.Column("importance", sa.Float(), server_default="0.5", nullable=False))
    op.add_column("memory_chunks", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_memory_chunks_content_hash", "memory_chunks", ["content_hash"])
    op.create_index("ix_memory_chunks_expires_at", "memory_chunks", ["expires_at"])
    op.execute(
        "CREATE INDEX ix_memory_chunks_embedding_hnsw "
        "ON memory_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade():
    op.drop_index("ix_memory_chunks_expires_at", table_name="memory_chunks")
    op.drop_index("ix_memory_chunks_content_hash", table_name="memory_chunks")
    op.execute("DROP INDEX IF EXISTS ix_memory_chunks_embedding_hnsw")
    op.drop_column("memory_chunks", "expires_at")
    op.drop_column("memory_chunks", "importance")
    op.drop_column("memory_chunks", "content_hash")
