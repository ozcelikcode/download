"""Isolate editor records and add reviewed content deletion.

Revision ID: s6d8f0b2c347
Revises: r5c7e9a1b236
"""

from alembic import op
import sqlalchemy as sa

revision = "s6d8f0b2c347"
down_revision = "r5c7e9a1b236"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("categories", "tags", "downloads", "media_assets"):
        with op.batch_alter_table(table, naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}) as batch:
            batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(f"fk_{table}_owner_id_users", "users", ["owner_id"], ["id"])
            batch.create_index(f"ix_{table}_owner_id", ["owner_id"])
            if table in {"categories", "tags"}:
                batch.drop_constraint(f"uq_{table}_name", type_="unique")
                batch.create_index(f"uq_{table}_owner_name", ["owner_id", "name"], unique=True)
                batch.create_index(f"uq_{table}_unowned_name", ["name"], unique=True, sqlite_where=sa.text("owner_id IS NULL"))
            if table == "downloads":
                batch.add_column(sa.Column("deletion_pending", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Legacy owners cannot be inferred reliably. Existing records remain staff-only.
    # Only known uploader identities can safely backfill media ownership.
    op.execute(sa.text("UPDATE media_assets SET owner_id=(SELECT id FROM users WHERE username=media_assets.uploaded_by)"))


def downgrade() -> None:
    raise RuntimeError("Editor ownership cannot be removed without weakening access boundaries")
