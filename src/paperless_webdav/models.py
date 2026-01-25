# src/paperless_webdav/models.py
"""SQLAlchemy database models."""

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from paperless_webdav.database import Base


SHARE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$")


class User(Base):
    """User linked to external auth provider."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    paperless_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Share(Base):
    """Share configuration for tag-filtered WebDAV access."""

    __tablename__ = "shares"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    include_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    exclude_tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    done_folder_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    done_folder_name: Mapped[str] = mapped_column(String(63), default="done")
    done_tag: Mapped[str | None] = mapped_column(String(63), nullable=True)
    allowed_users: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_shares_name", "name"),
        Index("idx_shares_owner", "owner_id"),
        Index("idx_shares_expires", "expires_at", postgresql_where=(expires_at.isnot(None))),
    )

    @validates("name")
    def validate_name(self, key: str, value: str) -> str:
        """Validate share name is alphanumeric with dashes only."""
        if not SHARE_NAME_PATTERN.match(value):
            raise ValueError(
                f"Share name must be alphanumeric with dashes, 1-63 chars. Got: {value!r}"
            )
        return value


class AuditLog(Base):
    """Security audit log for compliance and debugging."""

    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    share_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shares.id", ondelete="SET NULL"), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_user", "user_id"),
    )
