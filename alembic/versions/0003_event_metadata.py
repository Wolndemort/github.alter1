"""Add provenance and confidence to important events."""

from alembic import op
import sqlalchemy as sa


revision = "0003_event_metadata"
down_revision = "0002_important_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("important_events", sa.Column("source", sa.String(32), server_default="session_summary", nullable=False))
    op.add_column("important_events", sa.Column("confidence", sa.Float(), server_default="0.8", nullable=False))
    op.create_index("ix_important_events_user_title", "important_events", ["user_id", "title"])


def downgrade():
    op.drop_index("ix_important_events_user_title", table_name="important_events")
    op.drop_column("important_events", "confidence")
    op.drop_column("important_events", "source")
