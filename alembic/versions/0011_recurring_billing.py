"""Add opt-in recurring subscription billing."""
from alembic import op
import sqlalchemy as sa

revision = "0011_recurring_billing"
down_revision = "0010_billing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("payment_method_id", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("auto_renew", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("next_charge_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_next_charge_at", "users", ["next_charge_at"])


def downgrade():
    op.drop_index("ix_users_next_charge_at", table_name="users")
    op.drop_column("users", "next_charge_at")
    op.drop_column("users", "auto_renew")
    op.drop_column("users", "payment_method_id")
