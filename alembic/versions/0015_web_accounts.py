"""Add independent application accounts without changing Telegram identity."""
from alembic import op
import sqlalchemy as sa

revision = "0015_web_accounts"
down_revision = "0014_memory_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SEQUENCE IF NOT EXISTS users_id_seq")
    op.execute("SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 0) + 1, false)")
    op.execute("ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('users_id_seq')")
    op.create_table(
        "web_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_web_accounts_user_id", "web_accounts", ["user_id"])
    op.create_index("ix_web_accounts_email", "web_accounts", ["email"])


def downgrade():
    op.drop_index("ix_web_accounts_email", table_name="web_accounts")
    op.drop_index("ix_web_accounts_user_id", table_name="web_accounts")
    op.drop_table("web_accounts")
    op.execute("ALTER TABLE users ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS users_id_seq")
