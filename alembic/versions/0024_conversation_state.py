"""Keep structured state for the active conversation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0024_conversation_state"
down_revision = "0023_active_context_summary"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("session", sa.Column("conversation_state", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False))

def downgrade() -> None:
    op.drop_column("session", "conversation_state")
