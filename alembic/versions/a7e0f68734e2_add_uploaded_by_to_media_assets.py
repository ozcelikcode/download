"""add uploaded_by to media assets

Revision ID: a7e0f68734e2
Revises: c7636c94d128
Create Date: 2026-07-14 20:59:25.375070

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7e0f68734e2'
down_revision: Union[str, None] = 'c7636c94d128'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('uploaded_by', sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.drop_column('uploaded_by')
