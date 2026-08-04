"""Add reminder follow-up state."""
from alembic import op
import sqlalchemy as sa

revision = "0006_reminder_follow_up"
down_revision = "0005_pending_reminders"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("reminders", sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reminders", sa.Column("follow_up_sent", sa.Boolean(), server_default="false", nullable=False))

def downgrade():
    op.drop_column("reminders", "follow_up_sent")
    op.drop_column("reminders", "follow_up_at")
