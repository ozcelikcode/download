"""Add administrator-controlled editor publication policy."""
from alembic import op
import sqlalchemy as sa

revision = 'd7c9e1a3b458'
down_revision = 'c6b8d0f2a347'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('site_settings', sa.Column('editor_publication_policy', sa.String(20), nullable=False, server_default='verified_only'))


def downgrade() -> None:
    op.drop_column('site_settings', 'editor_publication_policy')
