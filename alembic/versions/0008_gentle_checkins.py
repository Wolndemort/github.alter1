"""Add opt-in gentle check-ins."""
from alembic import op
import sqlalchemy as sa

revision = "0008_gentle_checkins"
down_revision = "0007_checkins"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("users", sa.Column("checkins_enabled", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("users", sa.Column("last_checkin_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    op.drop_column("users", "last_checkin_at")
    op.drop_column("users", "checkins_enabled")
