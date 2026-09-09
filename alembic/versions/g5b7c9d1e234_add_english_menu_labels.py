"""Menü öğelerine İngilizce etiket ekle.

Revision ID: g5b7c9d1e234
Revises: f4a6b8c0d123
"""

from alembic import op
import sqlalchemy as sa

revision = "g5b7c9d1e234"
down_revision = "f4a6b8c0d123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("menu_items", sa.Column("label_en", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("menu_items", "label_en")
