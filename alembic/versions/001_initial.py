"""Initial database schema with users, shares, and audit_log tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-01-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(255), unique=True, nullable=False),
        sa.Column("paperless_token_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Create shares table
    op.create_table(
        "shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(63), unique=True, nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("include_tags", postgresql.JSONB(), nullable=False),
        sa.Column("exclude_tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("done_folder_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("done_folder_name", sa.String(63), nullable=False, server_default=sa.text("'done'")),
        sa.Column("done_tag", sa.String(63), nullable=True),
        sa.Column("allowed_users", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Create shares indexes
    op.create_index("idx_shares_name", "shares", ["name"])
    op.create_index("idx_shares_owner", "shares", ["owner_id"])
    op.create_index(
        "idx_shares_expires",
        "shares",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )

    # Create audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "share_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shares.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
    )

    # Create audit_log indexes
    op.create_index("idx_audit_timestamp", "audit_log", ["timestamp"])
    op.create_index("idx_audit_user", "audit_log", ["user_id"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_audit_user", table_name="audit_log")
    op.drop_index("idx_audit_timestamp", table_name="audit_log")

    # Drop tables in reverse order (respecting foreign key constraints)
    op.drop_table("audit_log")

    op.drop_index("idx_shares_expires", table_name="shares")
    op.drop_index("idx_shares_owner", table_name="shares")
    op.drop_index("idx_shares_name", table_name="shares")
    op.drop_table("shares")

    op.drop_table("users")
