"""Add editorial review, verification, and private staff correspondence.

Revision ID: t7e9a1c3d458
Revises: s6d8f0b2c347
"""

from alembic import op
import sqlalchemy as sa

revision = "t7e9a1c3d458"
down_revision = "s6d8f0b2c347"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("downloads", sa.Column("publication_pending", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("downloads", sa.Column("publication_feedback", sa.String(1000), nullable=True))
    op.create_index("ix_downloads_publication_pending", "downloads", ["publication_pending"])
    # Preserve categories and content; only the oldest required category stays protected.
    op.execute(sa.text("UPDATE categories SET is_required=0 WHERE is_required=1 AND id != (SELECT MIN(id) FROM categories WHERE is_required=1)"))
    # A required category is shared, irrespective of its original creator.
    # Keep its owner if clearing it would collide with an existing unowned name.
    op.execute(sa.text("UPDATE categories SET owner_id=NULL WHERE is_required=1 AND NOT EXISTS (SELECT 1 FROM categories other WHERE other.name=categories.name AND other.owner_id IS NULL AND other.id != categories.id)"))
    op.create_index("uq_categories_required", "categories", ["is_required"], unique=True, sqlite_where=sa.text("is_required = 1"))
    op.create_table(
        "editor_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subject", sa.String(150), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("responded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_editor_messages_sender_id", "editor_messages", ["sender_id"])
    op.create_index("ix_editor_messages_created_at", "editor_messages", ["created_at"])


def downgrade() -> None:
    raise RuntimeError("Editorial workflow data must not be discarded implicitly")
