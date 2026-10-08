"""Add content galleries, administrator limits and publisher report counters."""

from alembic import op
import sqlalchemy as sa

revision = 'c6b8d0f2a347'
down_revision = 'b5a7c9e1f236'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('site_settings', sa.Column('gallery_image_limit', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('downloads', sa.Column('gallery_images', sa.Text(), nullable=False, server_default='[]'))
    op.add_column('users', sa.Column('publisher_report_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'publisher_report_count')
    op.drop_column('downloads', 'gallery_images')
    op.drop_column('site_settings', 'gallery_image_limit')
