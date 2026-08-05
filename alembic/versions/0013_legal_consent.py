"""Store the time when a user accepted legal documents."""
from alembic import op
import sqlalchemy as sa

revision = "0013_legal_consent"
down_revision = "0012_subscription_reminders"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("legal_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("users", "legal_accepted_at")
