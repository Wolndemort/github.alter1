"""Add subscriptions and YooKassa payments."""
from alembic import op
import sqlalchemy as sa

revision = "0010_billing"
down_revision = "0009_vector_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_subscription_expires_at", "users", ["subscription_expires_at"])
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider_payment_id", sa.String(64), nullable=True),
        sa.Column("idempotence_key", sa.String(64), nullable=False),
        sa.Column("amount_rub", sa.String(20), nullable=False),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider_payment_id"),
        sa.UniqueConstraint("idempotence_key"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_status", "payments", ["status"])


def downgrade():
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_users_subscription_expires_at", table_name="users")
    op.drop_column("users", "subscription_expires_at")
