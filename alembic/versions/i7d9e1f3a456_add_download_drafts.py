"""Add automatic draft fields to downloads.

Revision ID: i7d9e1f3a456
Revises: h6c8d0e2f345
"""

from alembic import op
import sqlalchemy as sa


revision = "i7d9e1f3a456"
down_revision = "h6c8d0e2f345"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("downloads") as batch_op:
        batch_op.add_column(
            sa.Column("is_draft", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("draft_token", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_downloads_is_draft", ["is_draft"], unique=False)
        batch_op.create_unique_constraint("uq_downloads_draft_token", ["draft_token"])


def downgrade() -> None:
    with op.batch_alter_table("downloads") as batch_op:
        batch_op.drop_constraint("uq_downloads_draft_token", type_="unique")
        batch_op.drop_index("ix_downloads_is_draft")
        batch_op.drop_column("draft_token")
        batch_op.drop_column("is_draft")
