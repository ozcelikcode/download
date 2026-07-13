"""add icon extension short description

Revision ID: 1057201bb401
Revises: 93c6e5e23c06
Create Date: 2026-07-13 21:03:11.023059

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1057201bb401'
down_revision: Union[str, None] = '93c6e5e23c06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('downloads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('short_description', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('icon_extension', sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('downloads', schema=None) as batch_op:
        batch_op.drop_column('icon_extension')
        batch_op.drop_column('short_description')
