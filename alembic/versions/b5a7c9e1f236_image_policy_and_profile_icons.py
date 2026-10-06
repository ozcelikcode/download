"""Add administrator image policy and per-account profile icons."""

from alembic import op
import sqlalchemy as sa

revision = "b5a7c9e1f236"
down_revision = "a4f6b8d0e125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("image_compression_enabled", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("site_settings", sa.Column("image_compression_level", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("users", sa.Column("profile_icon", sa.String(50), nullable=False, server_default="user-circle"))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("profile_icon")
    with op.batch_alter_table("site_settings") as batch:
        batch.drop_column("image_compression_level")
        batch.drop_column("image_compression_enabled")
