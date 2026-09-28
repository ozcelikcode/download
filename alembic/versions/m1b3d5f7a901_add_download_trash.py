"""Add a recoverable trash state to downloads."""

from alembic import op
import sqlalchemy as sa

revision = "m1b3d5f7a901"
down_revision = "l0a2c4e6f789"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("downloads", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_downloads_deleted_at", "downloads", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_downloads_deleted_at", table_name="downloads")
    op.drop_column("downloads", "deleted_at")
