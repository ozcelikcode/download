"""Store a local, validated browser icon independently of the site logo."""

from alembic import op
import sqlalchemy as sa

revision = "a4f6b8d0e125"
down_revision = "z3e5a7c9d014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_settings", sa.Column("favicon_path", sa.String(500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("site_settings") as batch:
        batch.drop_column("favicon_path")
