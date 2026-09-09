"""İndirmelere güncel sürüm işareti ekle.

Revision ID: h6c8d0e2f345
Revises: g5b7c9d1e234
"""

from alembic import op
import sqlalchemy as sa

revision = "h6c8d0e2f345"
down_revision = "g5b7c9d1e234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "downloads",
        sa.Column("is_latest_version", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("downloads", "is_latest_version")
