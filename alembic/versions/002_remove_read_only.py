"""Remove read_only column from shares table.

Shares are always read-only by design - users cannot modify, delete, or upload
documents through WebDAV. The only write operation allowed is moving files
to/from the done folder, which just modifies tags in Paperless.

Revision ID: 002_remove_read_only
Revises: 001_initial
Create Date: 2026-01-25

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_remove_read_only"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove read_only column from shares table."""
    op.drop_column("shares", "read_only")


def downgrade() -> None:
    """Add read_only column back to shares table."""
    op.add_column(
        "shares",
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default="true"),
    )
