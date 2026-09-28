"""Add a protected installation lifecycle without reopening existing sites."""

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision = "l0a2c4e6f789"
down_revision = "k9f1b3d5e678"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("session_generation", sa.String(64), nullable=False, server_default=""))
    table = op.create_table(
        "site_lifecycle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("installed", sa.Boolean(), nullable=False),
        sa.Column("pending_reset", sa.String(20), nullable=True),
        sa.Column("purge_roots", sa.Text(), nullable=True),
    )
    bind = op.get_bind()
    stored = bind.execute(sa.text("SELECT admin_password_hash FROM site_settings LIMIT 1")).scalar()
    password_hash = stored or settings.admin_password_hash
    has_account = bool(password_hash and password_hash.startswith(("scrypt$", "$2a$", "$2b$", "$2y$")))
    has_content = bool(bind.execute(sa.text("SELECT COUNT(*) FROM downloads")).scalar())
    op.bulk_insert(table, [{"id": 1, "installed": has_account or has_content}])


def downgrade() -> None:
    op.drop_table("site_lifecycle")
    op.drop_column("site_settings", "session_generation")
