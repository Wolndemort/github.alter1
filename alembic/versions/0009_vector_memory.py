"""add vector memory"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0009_vector_memory"
down_revision = "0008_gentle_checkins"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "memory_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("source", sa.String(32), server_default="conversation", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_memory_chunks_user_id", "memory_chunks", ["user_id"])


def downgrade():
    op.drop_index("ix_memory_chunks_user_id", table_name="memory_chunks")
    op.drop_table("memory_chunks")
