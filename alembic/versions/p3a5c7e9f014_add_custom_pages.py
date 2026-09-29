"""Add standalone public and administrator-only pages.

Revision ID: p3a5c7e9f014
Revises: n2c4e6f8b012
"""

from alembic import op
import sqlalchemy as sa


revision = "p3a5c7e9f014"
down_revision = "n2c4e6f8b012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("visibility", sa.String(length=10), nullable=False, server_default="public"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("visibility IN ('public', 'private')", name="ck_pages_visibility"),
    )
    op.create_index("ix_pages_slug", "pages", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_pages_slug", table_name="pages")
    op.drop_table("pages")
