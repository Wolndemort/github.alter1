"""Persist one-time subscription expiry reminder markers."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012_subscription_reminders"
down_revision = "0011_recurring_billing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("subscription_reminders", JSONB(), server_default="{}", nullable=False))


def downgrade():
    op.drop_column("users", "subscription_reminders")
