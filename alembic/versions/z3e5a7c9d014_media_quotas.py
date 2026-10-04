"""Add administrator-configured personal media storage limits."""

from alembic import op
import sqlalchemy as sa

revision = "z3e5a7c9d014"
down_revision = "y2d4f6a8b903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("editor_media_quota_mb", sa.Integer(), nullable=False, server_default="256"))
    op.add_column("site_settings", sa.Column("manager_media_quota_mb", sa.Integer(), nullable=False, server_default="1024"))
    op.add_column("users", sa.Column("media_quota_mb", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("media_quota_mb")
    with op.batch_alter_table("site_settings") as batch:
        batch.drop_column("manager_media_quota_mb")
        batch.drop_column("editor_media_quota_mb")
