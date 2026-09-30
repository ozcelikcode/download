"""Remove the legacy single-administrator credential copy.

Revision ID: r5c7e9a1b236
Revises: q4b6d8f0a125
"""

from alembic import op


revision = "r5c7e9a1b236"
down_revision = "q4b6d8f0a125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("site_settings") as batch:
        batch.drop_column("admin_username")
        batch.drop_column("admin_password_hash")


def downgrade() -> None:
    raise RuntimeError("Removed credential copies cannot be safely restored")
