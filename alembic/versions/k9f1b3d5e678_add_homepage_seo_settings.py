"""Add editable homepage SEO metadata.

Revision ID: k9f1b3d5e678
Revises: j8e0f2a4b567
"""

from alembic import op
import sqlalchemy as sa


revision = "k9f1b3d5e678"
down_revision = "j8e0f2a4b567"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_settings",
        sa.Column("seo_home_title", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "site_settings",
        sa.Column("seo_meta_description", sa.String(length=320), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("site_settings", "seo_meta_description")
    op.drop_column("site_settings", "seo_home_title")
