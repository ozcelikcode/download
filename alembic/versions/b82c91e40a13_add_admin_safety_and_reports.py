"""Admin güvenliği, bağlantı raporu, dosya özeti ve işlem geçmişi.

Revision ID: b82c91e40a13
Revises: a7e0f68734e2
"""
from alembic import op
import sqlalchemy as sa

revision = "b82c91e40a13"
down_revision = "a7e0f68734e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Mevcut "extension" ikon türü eski VARCHAR(5) tanımını aşar.
    with op.batch_alter_table("downloads") as batch:
        batch.alter_column("icon_type", existing_type=sa.String(5), type_=sa.String(9), existing_nullable=False)
    op.add_column("media_assets", sa.Column("sha256", sa.String(64), nullable=True))
    op.add_column("media_assets", sa.Column("checksum_size", sa.BigInteger(), nullable=True))
    op.add_column("media_assets", sa.Column("checksum_mtime_ns", sa.BigInteger(), nullable=True))
    op.create_table("link_checks",
        sa.Column("download_id", sa.Integer(), sa.ForeignKey("downloads.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_link_checks_status", "link_checks", ["status"])
    op.create_table("login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    for field in ("ip_address", "attempted_at"):
        op.create_index(f"ix_login_attempts_{field}", "login_attempts", [field])
    op.create_table("audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("entity", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("changes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for field in ("actor", "entity", "created_at"):
        op.create_index(f"ix_audit_logs_{field}", "audit_logs", [field])


def downgrade() -> None:
    for table in ("audit_logs", "login_attempts", "link_checks"):
        op.drop_table(table)
    with op.batch_alter_table("media_assets") as batch:
        for field in ("checksum_mtime_ns", "checksum_size", "sha256"):
            batch.drop_column(field)
    with op.batch_alter_table("downloads") as batch:
        batch.alter_column("icon_type", existing_type=sa.String(9), type_=sa.String(5), existing_nullable=False)
