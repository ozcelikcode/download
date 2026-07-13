"""add admin account fields to site settings

Revision ID: c7636c94d128
Revises: d5fce4369d8b
Create Date: 2026-07-13 21:41:41.409514

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7636c94d128'
down_revision: Union[str, None] = 'd5fce4369d8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('admin_username', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('admin_password_hash', sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column('admin_icon', sa.String(length=50), nullable=False, server_default='user-circle')
        )
        batch_op.add_column(
            sa.Column('admin_icon_color', sa.String(length=20), nullable=False, server_default='slate')
        )
        batch_op.add_column(
            sa.Column('session_max_age_minutes', sa.Integer(), nullable=False, server_default='480')
        )


def downgrade() -> None:
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.drop_column('session_max_age_minutes')
        batch_op.drop_column('admin_icon_color')
        batch_op.drop_column('admin_icon')
        batch_op.drop_column('admin_password_hash')
        batch_op.drop_column('admin_username')
