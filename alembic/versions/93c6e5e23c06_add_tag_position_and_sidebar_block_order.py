"""add tag position and sidebar block order

Revision ID: 93c6e5e23c06
Revises: 1a4999d0411e
Create Date: 2026-07-12 18:42:40.777263

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93c6e5e23c06'
down_revision: Union[str, None] = '1a4999d0411e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


tags_table = sa.table(
    "tags",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("position", sa.Integer),
)


def upgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('position', sa.Integer(), nullable=False, server_default='0')
        )
        batch_op.create_index(batch_op.f('ix_tags_position'), ['position'], unique=False)

    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('sidebar_block_order', sa.String(length=100), nullable=False,
                      server_default='search,categories,tags')
        )

    # Etiket sıralaması: mevcut alfabetik görünümü koru (isim sırasına göre).
    tags = bind.execute(
        sa.select(tags_table.c.id).order_by(tags_table.c.name)
    ).fetchall()
    for position, (tag_id,) in enumerate(tags):
        bind.execute(
            tags_table.update()
            .where(tags_table.c.id == tag_id)
            .values(position=position)
        )


def downgrade() -> None:
    with op.batch_alter_table('site_settings', schema=None) as batch_op:
        batch_op.drop_column('sidebar_block_order')

    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tags_position'))
        batch_op.drop_column('position')
