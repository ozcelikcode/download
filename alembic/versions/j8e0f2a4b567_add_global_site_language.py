"""Add the global site language setting.

Revision ID: j8e0f2a4b567
Revises: i7d9e1f3a456
"""

from alembic import op
import sqlalchemy as sa


revision = "j8e0f2a4b567"
down_revision = "i7d9e1f3a456"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_settings",
        sa.Column("site_language", sa.String(length=2), nullable=False, server_default="tr"),
    )


def downgrade() -> None:
    op.drop_column("site_settings", "site_language")
