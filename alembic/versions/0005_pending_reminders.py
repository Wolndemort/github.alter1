"""Store reminder intents awaiting a time."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_pending_reminders"
down_revision = "0004_reminders"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("pending_reminder", postgresql.JSONB(), server_default="{}", nullable=False))


def downgrade():
    op.drop_column("users", "pending_reminder")
