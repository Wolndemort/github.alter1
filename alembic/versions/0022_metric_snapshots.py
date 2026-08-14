"""persistent owner diagnostics snapshots"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022_metric_snapshots"
down_revision = "0021_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("counters", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("latency", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_metric_snapshots_created_at", "metric_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_metric_snapshots_created_at", table_name="metric_snapshots")
    op.drop_table("metric_snapshots")
