"""Add hidden content and opt-in trash retention.

Revision ID: u8f0b2d4e569
Revises: t7e9a1c3d458
"""
from alembic import op
import sqlalchemy as sa

revision = "u8f0b2d4e569"
down_revision = "t7e9a1c3d458"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("downloads", sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("site_settings", sa.Column("trash_retention_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("site_settings", "trash_retention_days")
    op.drop_column("downloads", "is_hidden")
