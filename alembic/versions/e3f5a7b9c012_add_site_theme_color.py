"""Merkezi site renk teması.

Revision ID: e3f5a7b9c012
Revises: d2e4f6a8b901
"""

from alembic import op
import sqlalchemy as sa

revision = "e3f5a7b9c012"
down_revision = "d2e4f6a8b901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("theme_color", sa.String(length=20), nullable=False, server_default="blue"))


def downgrade() -> None:
    op.drop_column("site_settings", "theme_color")
