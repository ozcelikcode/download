"""Add pending registration requests without granting account access."""

from alembic import op
import sqlalchemy as sa

revision = "x1c3e5f7a892"
down_revision = "w0b2d4f6a781"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("registration_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_registration_requests_created_at", "registration_requests", ["created_at"])


def downgrade() -> None:
    op.drop_table("registration_requests")
