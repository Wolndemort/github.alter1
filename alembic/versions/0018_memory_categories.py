"""Track the structured category represented by episodic memory chunks."""
from alembic import op
import sqlalchemy as sa

revision = "0018_memory_categories"
down_revision = "0017_telegram_account_link"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("memory_chunks", sa.Column("category", sa.String(64), nullable=True))
    op.create_index("ix_memory_chunks_category", "memory_chunks", ["category"])


def downgrade():
    op.drop_index("ix_memory_chunks_category", table_name="memory_chunks")
    op.drop_column("memory_chunks", "category")
