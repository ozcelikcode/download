"""Keep the installation content language separate from the interface language.

Revision ID: n2c4e6f8b012
Revises: m1b3d5f7a901
"""

from alembic import op
import sqlalchemy as sa


revision = "n2c4e6f8b012"
down_revision = "m1b3d5f7a901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_settings",
        sa.Column("content_language", sa.String(length=2), nullable=False, server_default="en"),
    )
    op.execute("UPDATE site_settings SET content_language = site_language")
    op.execute(
        "UPDATE site_settings SET site_language = 'en', content_language = 'en' "
        "WHERE EXISTS (SELECT 1 FROM site_lifecycle WHERE installed = 0)"
    )
    with op.batch_alter_table("site_settings") as batch_op:
        batch_op.alter_column(
            "site_language", existing_type=sa.String(length=2),
            existing_nullable=False, server_default="en",
        )


def downgrade() -> None:
    with op.batch_alter_table("site_settings") as batch_op:
        batch_op.alter_column(
            "site_language", existing_type=sa.String(length=2),
            existing_nullable=False, server_default="tr",
        )
        batch_op.drop_column("content_language")
