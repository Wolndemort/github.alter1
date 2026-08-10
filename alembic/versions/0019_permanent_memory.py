"""Make all existing vector memory permanent."""
from alembic import op

revision = "0019_permanent_memory"
down_revision = "0018_memory_categories"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE memory_chunks SET expires_at = NULL WHERE expires_at IS NOT NULL")


def downgrade():
    # Existing facts remain permanent; no safe automatic expiry can be inferred.
    pass
