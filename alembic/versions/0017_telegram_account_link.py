"""Allow application accounts to link an existing Telegram identity."""
from alembic import op
import sqlalchemy as sa

revision = "0017_telegram_account_link"
down_revision = "0016_email_verification"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("web_accounts", sa.Column("telegram_user_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_web_accounts_telegram_user_id", "web_accounts", ["telegram_user_id"], unique=True)


def downgrade():
    op.drop_index("ix_web_accounts_telegram_user_id", table_name="web_accounts")
    op.drop_column("web_accounts", "telegram_user_id")
