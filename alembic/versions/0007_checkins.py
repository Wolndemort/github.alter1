"""Distinguish reminders from proactive check-ins."""
from alembic import op
import sqlalchemy as sa

revision = "0007_checkins"
down_revision = "0006_reminder_follow_up"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("reminders", sa.Column("kind", sa.String(16), server_default="reminder", nullable=False))

def downgrade():
    op.drop_column("reminders", "kind")
