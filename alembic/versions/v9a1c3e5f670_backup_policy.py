"""Store public-key-only backup scheduling policy.

Revision ID: v9a1c3e5f670
Revises: u8f0b2d4e569
"""
from alembic import op
import sqlalchemy as sa

revision = "v9a1c3e5f670"
down_revision = "u8f0b2d4e569"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("backup_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_key", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_attempt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_backup_policy_singleton"),
        sa.CheckConstraint("interval_days IN (1,3,5,7,14)", name="ck_backup_policy_interval"),
    )


def downgrade() -> None:
    op.drop_table("backup_policy")
