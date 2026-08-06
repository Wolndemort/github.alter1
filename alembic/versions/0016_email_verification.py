"""Add email verification state for independent application accounts."""
from alembic import op
import sqlalchemy as sa

revision = "0016_email_verification"
down_revision = "0015_web_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("web_accounts", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("web_accounts", sa.Column("verification_code_hash", sa.String(128), nullable=True))
    op.add_column("web_accounts", sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("web_accounts", sa.Column("verification_attempts", sa.Integer(), server_default="0", nullable=False))


def downgrade():
    op.drop_column("web_accounts", "verification_attempts")
    op.drop_column("web_accounts", "verification_expires_at")
    op.drop_column("web_accounts", "verification_code_hash")
    op.drop_column("web_accounts", "email_verified_at")
