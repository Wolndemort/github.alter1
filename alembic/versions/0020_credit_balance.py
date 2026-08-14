"""Add persistent purchased credit balance."""
from alembic import op
import sqlalchemy as sa

revision = "0020_credit_balance"
down_revision = "0019_permanent_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("credit_balance", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("users", "credit_balance")
