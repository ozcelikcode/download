"""Kategori koruması ve işlem geçmişi sınırı.

Revision ID: d2e4f6a8b901
Revises: b82c91e40a13
"""

from alembic import op
import sqlalchemy as sa


revision = "d2e4f6a8b901"
down_revision = "b82c91e40a13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Mevcut sitelerde ilk kategori korunur. Adı ve açıklaması sonradan serbestçe değiştirilebilir.
    op.execute("UPDATE categories SET is_required = 1 WHERE id = (SELECT id FROM categories ORDER BY id LIMIT 1)")
    op.add_column("site_settings", sa.Column("audit_log_max_records", sa.Integer(), nullable=False, server_default="200"))
    op.add_column("audit_logs", sa.Column("level", sa.String(length=20), nullable=False, server_default="success"))
    op.create_index("ix_audit_logs_level", "audit_logs", ["level"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_level", table_name="audit_logs")
    op.drop_column("audit_logs", "level")
    op.drop_column("site_settings", "audit_log_max_records")
    op.drop_column("categories", "is_required")
