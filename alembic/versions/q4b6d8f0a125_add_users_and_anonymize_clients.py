"""Add role-based users and replace stored client identifiers with keyed digests.

Revision ID: q4b6d8f0a125
Revises: p3a5c7e9f014
"""

import hashlib
import hmac

from alembic import op
import sqlalchemy as sa

from app.config import settings


revision = "q4b6d8f0a125"
down_revision = "p3a5c7e9f014"
branch_labels = None
depends_on = None


def _client_key(value: str, context: str) -> str:
    return hmac.new(settings.app_secret_key.encode(), f"{context}\0{value}".encode(), hashlib.sha256).hexdigest()


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deletion_requested_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('admin', 'manager', 'editor')", name="ck_users_role"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    connection = op.get_bind()
    installed = connection.execute(sa.text("SELECT installed FROM site_lifecycle WHERE id=1")).scalar()
    account = connection.execute(sa.text("SELECT admin_username, admin_password_hash FROM site_settings WHERE id=1")).first()
    if installed and account:
        username = account.admin_username or settings.admin_username
        password_hash = account.admin_password_hash or settings.admin_password_hash
        if not password_hash or "placeholder" in password_hash:
            raise RuntimeError("Cannot migrate an installed site without a valid admin password hash")
        connection.execute(
            sa.text("INSERT INTO users (username, password_hash, role, is_active) VALUES (:username, :password_hash, 'admin', 1)"),
            {"username": username, "password_hash": password_hash},
        )

    # Preserve rate-limit history without retaining the original addresses.
    login_rows = connection.execute(sa.text("SELECT id, ip_address FROM login_attempts")).all()
    download_rows = connection.execute(sa.text("SELECT id, ip_address FROM download_logs")).all()
    op.alter_column("login_attempts", "ip_address", new_column_name="client_key", existing_type=sa.String(45))
    op.drop_index("ix_login_attempts_ip_address", table_name="login_attempts")
    with op.batch_alter_table("login_attempts") as batch:
        batch.alter_column("client_key", type_=sa.String(64), existing_type=sa.String(45))
    op.create_index("ix_login_attempts_client_key", "login_attempts", ["client_key"])
    for row in login_rows:
        connection.execute(sa.text("UPDATE login_attempts SET client_key=:key WHERE id=:id"), {"key": _client_key(row.ip_address, "login"), "id": row.id})

    op.drop_index("ix_download_logs_ip_time", table_name="download_logs")
    with op.batch_alter_table("download_logs") as batch:
        batch.alter_column("ip_address", new_column_name="client_key", type_=sa.String(64), existing_type=sa.String(45))
        batch.drop_column("user_agent")
    op.create_index("ix_download_logs_client_time", "download_logs", ["client_key", "downloaded_at"])
    for row in download_rows:
        connection.execute(sa.text("UPDATE download_logs SET client_key=:key WHERE id=:id"), {"key": _client_key(row.ip_address, "download"), "id": row.id})

    # Old audit events may include raw addresses; redact them in place.
    for row in connection.execute(sa.text("SELECT id, changes FROM audit_logs WHERE changes LIKE '%ip_address%'")).all():
        connection.execute(sa.text("UPDATE audit_logs SET changes='{}' WHERE id=:id"), {"id": row.id})


def downgrade() -> None:
    raise RuntimeError("Privacy migration cannot restore removed client addresses")
