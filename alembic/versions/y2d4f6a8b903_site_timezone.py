"""Add a display time zone without changing stored UTC timestamps."""

from alembic import op
import sqlalchemy as sa

revision = "y2d4f6a8b903"
down_revision = "x1c3e5f7a892"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("site_timezone", sa.String(64), nullable=False, server_default="UTC"))


def downgrade() -> None:
    with op.batch_alter_table("site_settings") as batch:
        batch.drop_column("site_timezone")
