"""Add reminders."""

from alembic import op
import sqlalchemy as sa

revision = "0004_reminders"
down_revision = "0003_event_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_sent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reminders_user_id", "reminders", ["user_id"])
    op.create_index("ix_reminders_remind_at", "reminders", ["remind_at"])
    op.create_index("ix_reminders_is_sent", "reminders", ["is_sent"])


def downgrade():
    op.drop_table("reminders")
