"""Add structured important events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_important_events"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "important_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("importance", sa.String(length=16), server_default="normal", nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_important_events_user_id", "important_events", ["user_id"])


def downgrade():
    op.drop_index("ix_important_events_user_id", table_name="important_events")
    op.drop_table("important_events")
