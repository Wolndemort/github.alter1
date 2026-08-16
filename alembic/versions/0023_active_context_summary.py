"""Store active conversation summaries separately from durable memory."""

from alembic import op
import sqlalchemy as sa


revision = "0023_active_context_summary"
down_revision = "0022_metric_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("session", sa.Column("context_summary", sa.Text(), nullable=True))
    op.add_column("session", sa.Column("context_summary_messages", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("session", "context_summary_messages")
    op.drop_column("session", "context_summary")
