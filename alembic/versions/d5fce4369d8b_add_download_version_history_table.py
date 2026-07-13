"""add download version history table

Revision ID: d5fce4369d8b
Revises: 1057201bb401
Create Date: 2026-07-13 21:27:55.842791

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5fce4369d8b'
down_revision: Union[str, None] = '1057201bb401'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'download_version_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('download_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['download_id'], ['downloads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('download_version_history', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_download_version_history_download_id'), ['download_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('download_version_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_download_version_history_download_id'))
    op.drop_table('download_version_history')
