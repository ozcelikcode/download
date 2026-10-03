"""Track a committed restore for crash-safe media recovery."""
from alembic import op
import sqlalchemy as sa

revision = "w0b2d4f6a781"
down_revision = "v9a1c3e5f670"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("restore_marker", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("site_settings", "restore_marker")
