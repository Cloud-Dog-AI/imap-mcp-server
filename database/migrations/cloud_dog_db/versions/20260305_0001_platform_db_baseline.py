"""imap-mcp-server cloud_dog_db baseline

Revision ID: 20260305_0001
Revises:
Create Date: 2026-03-05 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260305_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imap_platform_db_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service"),
    )
    op.create_index(
        op.f("ix_imap_platform_db_state_created_at"),
        "imap_platform_db_state",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_imap_platform_db_state_created_at"), table_name="imap_platform_db_state")
    op.drop_table("imap_platform_db_state")
