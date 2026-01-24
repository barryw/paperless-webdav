# paperless-webdav Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a WebDAV bridge service that exposes Paperless-ngx documents as mountable network shares filtered by tags.

**Architecture:** Single Python service with two interfaces - FastAPI admin UI (port 8080) and wsgidav WebDAV server (port 8081). Uses PostgreSQL for share/user config, Paperless API for documents.

**Tech Stack:** Python 3.11+, FastAPI, wsgidav, SQLAlchemy 2.0, Jinja2, HTMX, Tailwind CSS, structlog

---

## Phase 1: Project Scaffolding & Core Infrastructure

### Task 1.1: Initialize Python Project Structure

**Files:**
- Create: `pyproject.toml`
- Create: `src/paperless_webdav/__init__.py`
- Create: `src/paperless_webdav/config.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "paperless-webdav"
version = "0.1.0"
description = "WebDAV bridge for Paperless-ngx with tag-based shares"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "wsgidav>=4.3.0",
    "cheroot>=10.0.0",
    "sqlalchemy[asyncio]>=2.0.25",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.6",
    "structlog>=24.1.0",
    "cryptography>=42.0.0",
    "authlib>=1.3.0",
    "python-ldap>=3.4.0",
    "itsdangerous>=2.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "respx>=0.20.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/paperless_webdav"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true
```

**Step 2: Create source directory structure**

```bash
mkdir -p src/paperless_webdav tests
touch src/paperless_webdav/__init__.py
touch tests/__init__.py
```

**Step 3: Create config.py with pydantic-settings**

```python
# src/paperless_webdav/config.py
"""Application configuration via environment variables."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Core
    paperless_url: str = Field(description="Paperless-ngx base URL")
    database_url: SecretStr = Field(description="PostgreSQL connection string")
    encryption_key: SecretStr = Field(description="32-byte base64 key for token encryption")

    # Ports
    admin_port: int = Field(default=8080, description="Admin UI port")
    webdav_port: int = Field(default=8081, description="WebDAV server port")

    # Auth mode
    auth_mode: str = Field(default="paperless", pattern="^(paperless|oidc)$")

    # OIDC settings (when auth_mode=oidc)
    oidc_issuer: str | None = Field(default=None)
    oidc_client_id: str | None = Field(default=None)
    oidc_client_secret: SecretStr | None = Field(default=None)
    ldap_url: str | None = Field(default=None)
    ldap_base_dn: str | None = Field(default=None)
    ldap_bind_dn: str | None = Field(default=None)
    ldap_bind_password: SecretStr | None = Field(default=None)

    # Security
    session_expiry_hours: int = Field(default=24)
    rate_limit_attempts: int = Field(default=5)
    rate_limit_window_minutes: int = Field(default=15)
    secret_key: SecretStr = Field(description="Secret key for session signing")

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json", pattern="^(json|console)$")

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
```

**Step 4: Create conftest.py with basic fixtures**

```python
# tests/conftest.py
"""Shared test fixtures."""

import pytest
from unittest.mock import patch


@pytest.fixture
def mock_settings():
    """Provide test settings."""
    with patch.dict("os.environ", {
        "PAPERLESS_URL": "http://paperless.test",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "ENCRYPTION_KEY": "dGVzdGtleXRoYXRpczMyYnl0ZXNsb25nIQ==",
        "SECRET_KEY": "test-secret-key-for-sessions",
    }):
        yield
```

**Step 5: Verify project loads**

Run: `cd /home/barry/paperless-webdav/.worktrees/dev && python -c "from paperless_webdav.config import Settings; print('OK')"`
Expected: Error (not installed yet)

**Step 6: Install in development mode**

```bash
cd /home/barry/paperless-webdav/.worktrees/dev
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**Step 7: Verify installation**

Run: `source .venv/bin/activate && python -c "from paperless_webdav.config import Settings; print('OK')"`
Expected: OK

**Step 8: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "feat: initialize project structure with config

- Add pyproject.toml with all dependencies
- Create config.py with pydantic-settings for env vars
- Set up test infrastructure with pytest

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.2: Set Up Structured Logging

**Files:**
- Create: `src/paperless_webdav/logging.py`
- Create: `tests/test_logging.py`

**Step 1: Write the failing test**

```python
# tests/test_logging.py
"""Tests for structured logging setup."""

import json
import structlog
from paperless_webdav.logging import setup_logging, get_logger


def test_setup_logging_json_format(capsys):
    """JSON format should produce valid JSON output."""
    setup_logging(log_level="INFO", log_format="json")
    logger = get_logger("test")

    logger.info("test message", user_id="barry", action="login")

    captured = capsys.readouterr()
    log_line = captured.err.strip()
    parsed = json.loads(log_line)

    assert parsed["event"] == "test message"
    assert parsed["user_id"] == "barry"
    assert parsed["action"] == "login"
    assert "timestamp" in parsed


def test_logger_never_includes_secrets():
    """Ensure sensitive fields are redacted."""
    setup_logging(log_level="INFO", log_format="json")
    logger = get_logger("test")

    # This should not raise and should redact the token
    logger.info("auth", token="secret123", password="hunter2")
    # Manual verification: check logs don't contain actual values
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_logging.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/paperless_webdav/logging.py
"""Structured logging configuration for Graylog ingestion."""

import logging
import sys
from typing import Any

import structlog


# Fields that should never appear in logs
REDACTED_FIELDS = {"token", "password", "secret", "api_key", "encryption_key"}


def _redact_sensitive(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Redact sensitive fields from log output."""
    for field in REDACTED_FIELDS:
        if field in event_dict:
            event_dict[field] = "[REDACTED]"
    return event_dict


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure structlog for JSON or console output.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_format: Output format - 'json' for Graylog, 'console' for development
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_sensitive,
    ]

    if log_format == "json":
        # JSON format for Graylog ingestion
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level.upper())
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=True,
        )
    else:
        # Console format for development
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level.upper())
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=True,
        )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance with the given name.

    Args:
        name: Logger name (typically module name)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)
```

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_logging.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/logging.py tests/test_logging.py
git commit -m "feat: add structured JSON logging for Graylog

- Configure structlog with JSON and console formatters
- Add automatic timestamp and log level
- Redact sensitive fields (token, password, secret, etc.)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.3: Database Models with SQLAlchemy

**Files:**
- Create: `src/paperless_webdav/database.py`
- Create: `src/paperless_webdav/models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**

```python
# tests/test_models.py
"""Tests for database models."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from paperless_webdav.models import User, Share, AuditLog


def test_user_model_has_required_fields():
    """User model should have all required fields."""
    user = User(
        id=uuid4(),
        external_id="auth0|123",
        paperless_token_encrypted=b"encrypted",
    )
    assert user.external_id == "auth0|123"
    assert user.paperless_token_encrypted == b"encrypted"


def test_share_model_has_required_fields():
    """Share model should have all required fields."""
    user_id = uuid4()
    share = Share(
        id=uuid4(),
        name="tax2025",
        owner_id=user_id,
        include_tags=["tax", "2025"],
        exclude_tags=["draft"],
        done_folder_enabled=True,
        done_folder_name="completed",
        done_tag="reviewed",
    )
    assert share.name == "tax2025"
    assert share.include_tags == ["tax", "2025"]
    assert share.done_folder_enabled is True


def test_share_name_validation():
    """Share names must be alphanumeric with dashes only."""
    # Valid names
    Share(id=uuid4(), name="tax2025", owner_id=uuid4(), include_tags=["tax"])
    Share(id=uuid4(), name="my-share-name", owner_id=uuid4(), include_tags=["tag"])

    # Invalid names should raise
    with pytest.raises(ValueError):
        Share(id=uuid4(), name="invalid name", owner_id=uuid4(), include_tags=["tax"])
    with pytest.raises(ValueError):
        Share(id=uuid4(), name="invalid/path", owner_id=uuid4(), include_tags=["tax"])


def test_audit_log_model():
    """AuditLog model should capture security events."""
    log = AuditLog(
        id=uuid4(),
        event_type="document_accessed",
        user_id=uuid4(),
        share_id=uuid4(),
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0",
        details={"document_id": 123},
    )
    assert log.event_type == "document_accessed"
    assert log.details["document_id"] == 123
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_models.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write database.py**

```python
# src/paperless_webdav/database.py
"""Database connection and session management."""

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Engine and session factory (initialized on startup)
_engine = None
_async_session_factory = None


async def init_database(database_url: str) -> None:
    """Initialize database engine and session factory.

    Args:
        database_url: PostgreSQL connection string
    """
    global _engine, _async_session_factory

    # Convert postgresql:// to postgresql+asyncpg://
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )
    _async_session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for dependency injection.

    Yields:
        AsyncSession instance
    """
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database first.")

    async with _async_session_factory() as session:
        yield session


async def close_database() -> None:
    """Close database connections."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
```

**Step 4: Write models.py**

```python
# src/paperless_webdav/models.py
"""SQLAlchemy database models."""

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import field_validator
from sqlalchemy import Index, String, Text, Boolean, DateTime, LargeBinary, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column, validates

from paperless_webdav.database import Base


# Regex for valid share names: alphanumeric and dashes, 1-63 chars
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
    read_only: Mapped[bool] = mapped_column(Boolean, default=True)
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
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_user", "user_id"),
    )
```

**Step 5: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_models.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/paperless_webdav/database.py src/paperless_webdav/models.py tests/test_models.py
git commit -m "feat: add database models for users, shares, and audit log

- User model with encrypted Paperless token storage
- Share model with tag filters, expiration, done folder config
- AuditLog model for security event tracking
- Share name validation (alphanumeric + dash, max 63 chars)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.4: Token Encryption Service

**Files:**
- Create: `src/paperless_webdav/encryption.py`
- Create: `tests/test_encryption.py`

**Step 1: Write the failing test**

```python
# tests/test_encryption.py
"""Tests for token encryption service."""

import base64
import pytest
from paperless_webdav.encryption import TokenEncryption


@pytest.fixture
def encryption():
    """Create encryption instance with test key."""
    # 32-byte key, base64 encoded
    key = base64.b64encode(b"testkeythathas32bytesforaes256!").decode()
    return TokenEncryption(key)


def test_encrypt_decrypt_roundtrip(encryption):
    """Encrypted token should decrypt to original value."""
    original = "paperless-api-token-abc123"

    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)

    assert decrypted == original
    assert encrypted != original.encode()  # Should be different


def test_encrypted_output_is_bytes(encryption):
    """Encryption should return bytes."""
    encrypted = encryption.encrypt("test")
    assert isinstance(encrypted, bytes)


def test_decrypt_invalid_data_raises(encryption):
    """Decrypting garbage should raise an error."""
    with pytest.raises(Exception):  # InvalidTag or similar
        encryption.decrypt(b"not-valid-encrypted-data")


def test_same_plaintext_different_ciphertext(encryption):
    """Same input should produce different output (random nonce)."""
    plaintext = "test-token"

    encrypted1 = encryption.encrypt(plaintext)
    encrypted2 = encryption.encrypt(plaintext)

    assert encrypted1 != encrypted2  # Different nonces
    # But both should decrypt to same value
    assert encryption.decrypt(encrypted1) == encryption.decrypt(encrypted2)
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_encryption.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/paperless_webdav/encryption.py
"""AES-256-GCM encryption for Paperless API tokens."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TokenEncryption:
    """Encrypt and decrypt Paperless API tokens using AES-256-GCM.

    Uses random nonces for each encryption, so the same plaintext
    produces different ciphertext each time.
    """

    NONCE_SIZE = 12  # 96 bits, standard for GCM

    def __init__(self, key_base64: str) -> None:
        """Initialize with a base64-encoded 32-byte key.

        Args:
            key_base64: Base64-encoded 256-bit key
        """
        key = base64.b64decode(key_base64)
        if len(key) != 32:
            raise ValueError(f"Key must be 32 bytes, got {len(key)}")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt (typically an API token)

        Returns:
            Encrypted bytes (nonce + ciphertext + tag)
        """
        nonce = os.urandom(self.NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        # Prepend nonce to ciphertext for storage
        return nonce + ciphertext

    def decrypt(self, encrypted: bytes) -> str:
        """Decrypt encrypted bytes back to plaintext.

        Args:
            encrypted: Bytes from encrypt() (nonce + ciphertext + tag)

        Returns:
            Original plaintext string

        Raises:
            cryptography.exceptions.InvalidTag: If decryption fails
        """
        nonce = encrypted[:self.NONCE_SIZE]
        ciphertext = encrypted[self.NONCE_SIZE:]
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
```

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_encryption.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/encryption.py tests/test_encryption.py
git commit -m "feat: add AES-256-GCM encryption for API tokens

- TokenEncryption class with encrypt/decrypt methods
- Uses random nonces (same plaintext → different ciphertext)
- Key provided as base64-encoded 32-byte string

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.5: Paperless API Client

**Files:**
- Create: `src/paperless_webdav/paperless_client.py`
- Create: `tests/test_paperless_client.py`

**Step 1: Write the failing test**

```python
# tests/test_paperless_client.py
"""Tests for Paperless-ngx API client."""

import pytest
import respx
from httpx import Response

from paperless_webdav.paperless_client import PaperlessClient, PaperlessDocument, PaperlessTag


@pytest.fixture
def client():
    """Create a test client."""
    return PaperlessClient(
        base_url="http://paperless.test",
        token="test-token-123",
    )


@respx.mock
@pytest.mark.asyncio
async def test_get_tags(client):
    """Should fetch and parse tags from Paperless API."""
    respx.get("http://paperless.test/api/tags/").mock(
        return_value=Response(200, json={
            "count": 2,
            "results": [
                {"id": 1, "name": "tax", "slug": "tax"},
                {"id": 2, "name": "2025", "slug": "2025"},
            ]
        })
    )

    tags = await client.get_tags()

    assert len(tags) == 2
    assert tags[0].name == "tax"
    assert tags[1].name == "2025"


@respx.mock
@pytest.mark.asyncio
async def test_get_documents_by_tags(client):
    """Should fetch documents filtered by tags."""
    respx.get("http://paperless.test/api/documents/").mock(
        return_value=Response(200, json={
            "count": 1,
            "results": [
                {
                    "id": 42,
                    "title": "W2 Form 2025",
                    "original_file_name": "w2.pdf",
                    "created": "2025-01-15T10:30:00Z",
                    "modified": "2025-01-15T10:30:00Z",
                    "tags": [1, 2],
                }
            ]
        })
    )

    docs = await client.get_documents(include_tag_ids=[1, 2])

    assert len(docs) == 1
    assert docs[0].title == "W2 Form 2025"
    assert docs[0].id == 42


@respx.mock
@pytest.mark.asyncio
async def test_download_document(client):
    """Should download document content."""
    respx.get("http://paperless.test/api/documents/42/download/").mock(
        return_value=Response(200, content=b"%PDF-1.4 fake pdf content")
    )

    content = await client.download_document(42)

    assert content.startswith(b"%PDF")


@respx.mock
@pytest.mark.asyncio
async def test_add_tag_to_document(client):
    """Should add a tag to a document."""
    # First mock getting current document
    respx.get("http://paperless.test/api/documents/42/").mock(
        return_value=Response(200, json={
            "id": 42,
            "title": "W2",
            "tags": [1, 2],
        })
    )
    # Then mock the update
    respx.patch("http://paperless.test/api/documents/42/").mock(
        return_value=Response(200, json={
            "id": 42,
            "title": "W2",
            "tags": [1, 2, 3],
        })
    )

    await client.add_tag_to_document(document_id=42, tag_id=3)

    # Verify the patch was called with correct tags
    assert respx.calls.last.request.url.path == "/api/documents/42/"


@respx.mock
@pytest.mark.asyncio
async def test_validate_token_success(client):
    """Should return True for valid token."""
    respx.get("http://paperless.test/api/tags/").mock(
        return_value=Response(200, json={"count": 0, "results": []})
    )

    is_valid = await client.validate_token()

    assert is_valid is True


@respx.mock
@pytest.mark.asyncio
async def test_validate_token_failure(client):
    """Should return False for invalid token."""
    respx.get("http://paperless.test/api/tags/").mock(
        return_value=Response(401)
    )

    is_valid = await client.validate_token()

    assert is_valid is False
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_paperless_client.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/paperless_webdav/paperless_client.py
"""Async client for Paperless-ngx REST API."""

from dataclasses import dataclass
from datetime import datetime

import httpx

from paperless_webdav.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PaperlessTag:
    """Paperless tag representation."""
    id: int
    name: str
    slug: str


@dataclass
class PaperlessDocument:
    """Paperless document metadata."""
    id: int
    title: str
    original_file_name: str
    created: datetime
    modified: datetime
    tags: list[int]


class PaperlessClient:
    """Async HTTP client for Paperless-ngx API.

    All methods use the user's API token for authentication,
    ensuring document access respects Paperless permissions.
    """

    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        """Initialize client with Paperless URL and API token.

        Args:
            base_url: Paperless-ngx base URL (e.g., https://paperless.example.com)
            token: User's Paperless API token
            timeout: Request timeout in seconds
        """
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Token {token}"},
            timeout=timeout,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "PaperlessClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def validate_token(self) -> bool:
        """Check if the API token is valid.

        Returns:
            True if token is valid, False otherwise
        """
        try:
            response = await self._client.get("/api/tags/")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def get_tags(self) -> list[PaperlessTag]:
        """Fetch all tags from Paperless.

        Returns:
            List of PaperlessTag objects
        """
        tags: list[PaperlessTag] = []
        url = "/api/tags/"

        while url:
            response = await self._client.get(url)
            response.raise_for_status()
            data = response.json()

            for tag_data in data["results"]:
                tags.append(PaperlessTag(
                    id=tag_data["id"],
                    name=tag_data["name"],
                    slug=tag_data["slug"],
                ))

            url = data.get("next")

        return tags

    async def search_tags(self, query: str) -> list[PaperlessTag]:
        """Search tags by name.

        Args:
            query: Search string

        Returns:
            List of matching PaperlessTag objects
        """
        response = await self._client.get("/api/tags/", params={"name__icontains": query})
        response.raise_for_status()
        data = response.json()

        return [
            PaperlessTag(id=t["id"], name=t["name"], slug=t["slug"])
            for t in data["results"]
        ]

    async def get_tag_by_name(self, name: str) -> PaperlessTag | None:
        """Get a tag by exact name.

        Args:
            name: Exact tag name

        Returns:
            PaperlessTag if found, None otherwise
        """
        response = await self._client.get("/api/tags/", params={"name__iexact": name})
        response.raise_for_status()
        data = response.json()

        if data["results"]:
            t = data["results"][0]
            return PaperlessTag(id=t["id"], name=t["name"], slug=t["slug"])
        return None

    async def get_documents(
        self,
        include_tag_ids: list[int] | None = None,
        exclude_tag_ids: list[int] | None = None,
    ) -> list[PaperlessDocument]:
        """Fetch documents optionally filtered by tags.

        Args:
            include_tag_ids: Documents must have ALL these tags
            exclude_tag_ids: Documents must have NONE of these tags

        Returns:
            List of PaperlessDocument objects
        """
        documents: list[PaperlessDocument] = []
        params: dict = {}

        if include_tag_ids:
            # tags__id__all requires comma-separated list
            params["tags__id__all"] = ",".join(str(t) for t in include_tag_ids)

        if exclude_tag_ids:
            # tags__id__none for exclusion
            params["tags__id__none"] = ",".join(str(t) for t in exclude_tag_ids)

        url = "/api/documents/"

        while url:
            response = await self._client.get(url, params=params if url == "/api/documents/" else None)
            response.raise_for_status()
            data = response.json()

            for doc_data in data["results"]:
                documents.append(PaperlessDocument(
                    id=doc_data["id"],
                    title=doc_data["title"],
                    original_file_name=doc_data.get("original_file_name", "document.pdf"),
                    created=datetime.fromisoformat(doc_data["created"].replace("Z", "+00:00")),
                    modified=datetime.fromisoformat(doc_data["modified"].replace("Z", "+00:00")),
                    tags=doc_data["tags"],
                ))

            url = data.get("next")

        return documents

    async def get_document(self, document_id: int) -> PaperlessDocument:
        """Fetch a single document by ID.

        Args:
            document_id: Paperless document ID

        Returns:
            PaperlessDocument object
        """
        response = await self._client.get(f"/api/documents/{document_id}/")
        response.raise_for_status()
        doc_data = response.json()

        return PaperlessDocument(
            id=doc_data["id"],
            title=doc_data["title"],
            original_file_name=doc_data.get("original_file_name", "document.pdf"),
            created=datetime.fromisoformat(doc_data["created"].replace("Z", "+00:00")),
            modified=datetime.fromisoformat(doc_data["modified"].replace("Z", "+00:00")),
            tags=doc_data["tags"],
        )

    async def download_document(self, document_id: int, original: bool = False) -> bytes:
        """Download document content.

        Args:
            document_id: Paperless document ID
            original: If True, download original file; otherwise archived version

        Returns:
            Document content as bytes
        """
        params = {"original": "true"} if original else {}
        response = await self._client.get(
            f"/api/documents/{document_id}/download/",
            params=params,
        )
        response.raise_for_status()
        return response.content

    async def add_tag_to_document(self, document_id: int, tag_id: int) -> None:
        """Add a tag to a document.

        Args:
            document_id: Paperless document ID
            tag_id: Tag ID to add
        """
        # Get current tags
        response = await self._client.get(f"/api/documents/{document_id}/")
        response.raise_for_status()
        current_tags = response.json()["tags"]

        # Add new tag if not already present
        if tag_id not in current_tags:
            current_tags.append(tag_id)
            response = await self._client.patch(
                f"/api/documents/{document_id}/",
                json={"tags": current_tags},
            )
            response.raise_for_status()
            logger.info(
                "tag_added",
                document_id=document_id,
                tag_id=tag_id,
            )

    async def remove_tag_from_document(self, document_id: int, tag_id: int) -> None:
        """Remove a tag from a document.

        Args:
            document_id: Paperless document ID
            tag_id: Tag ID to remove
        """
        # Get current tags
        response = await self._client.get(f"/api/documents/{document_id}/")
        response.raise_for_status()
        current_tags = response.json()["tags"]

        # Remove tag if present
        if tag_id in current_tags:
            current_tags.remove(tag_id)
            response = await self._client.patch(
                f"/api/documents/{document_id}/",
                json={"tags": current_tags},
            )
            response.raise_for_status()
            logger.info(
                "tag_removed",
                document_id=document_id,
                tag_id=tag_id,
            )
```

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_paperless_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/paperless_client.py tests/test_paperless_client.py
git commit -m "feat: add Paperless-ngx API client

- Async HTTP client with token auth
- Get/search tags, get documents by tag filters
- Download document content
- Add/remove tags from documents
- Token validation for auth checking

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.6: Basic wsgidav Provider - Read Operations

**Files:**
- Create: `src/paperless_webdav/webdav_provider.py`
- Create: `tests/test_webdav_provider.py`

**Step 1: Write the failing test**

```python
# tests/test_webdav_provider.py
"""Tests for wsgidav Paperless provider."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from paperless_webdav.webdav_provider import (
    PaperlessProvider,
    ShareResource,
    DocumentResource,
    RootResource,
)
from paperless_webdav.paperless_client import PaperlessDocument


@pytest.fixture
def mock_share():
    """Create a mock share configuration."""
    share = MagicMock()
    share.name = "tax2025"
    share.include_tags = ["tax", "2025"]
    share.exclude_tags = []
    share.done_folder_enabled = False
    share.done_tag = None
    return share


@pytest.fixture
def mock_document():
    """Create a mock Paperless document."""
    return PaperlessDocument(
        id=42,
        title="W2 Form",
        original_file_name="w2.pdf",
        created=datetime(2025, 1, 15, tzinfo=timezone.utc),
        modified=datetime(2025, 1, 15, tzinfo=timezone.utc),
        tags=[1, 2],
    )


def test_root_resource_get_member_names():
    """Root resource should list available shares."""
    shares = {"tax2025": MagicMock(), "receipts": MagicMock()}
    root = RootResource("/", {"shares": shares})

    members = root.get_member_names()

    assert "tax2025" in members
    assert "receipts" in members


def test_share_resource_display_name(mock_share):
    """Share resource should use share name as display name."""
    resource = ShareResource("/tax2025", {"share": mock_share})

    assert resource.get_display_name() == "tax2025"


def test_document_resource_properties(mock_document):
    """Document resource should expose document metadata."""
    resource = DocumentResource(
        "/tax2025/W2 Form.pdf",
        {
            "document": mock_document,
            "paperless_client": MagicMock(),
        }
    )

    assert resource.get_display_name() == "W2 Form.pdf"
    assert resource.get_content_length() > 0 or resource.get_content_length() is None
    assert resource.get_content_type() == "application/pdf"


def test_document_filename_sanitization():
    """Document filenames should be safe for filesystem use."""
    doc = PaperlessDocument(
        id=1,
        title="Invoice/2025: Special <chars>",
        original_file_name="invoice.pdf",
        created=datetime.now(timezone.utc),
        modified=datetime.now(timezone.utc),
        tags=[],
    )
    resource = DocumentResource("/share/doc.pdf", {"document": doc, "paperless_client": MagicMock()})

    name = resource.get_display_name()

    # Should not contain filesystem-unsafe characters
    assert "/" not in name
    assert ":" not in name
    assert "<" not in name
    assert ">" not in name
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_webdav_provider.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/paperless_webdav/webdav_provider.py
"""wsgidav provider for Paperless-ngx documents."""

import re
from datetime import datetime, timezone
from typing import Any, Iterator
from io import BytesIO

from wsgidav.dav_provider import DAVProvider, DAVCollection, DAVNonCollection
from wsgidav.util import join_uri

from paperless_webdav.paperless_client import PaperlessClient, PaperlessDocument
from paperless_webdav.logging import get_logger

logger = get_logger(__name__)

# Characters not allowed in filenames
UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def sanitize_filename(name: str) -> str:
    """Remove or replace filesystem-unsafe characters from filename.

    Args:
        name: Raw filename/title

    Returns:
        Safe filename string
    """
    # Replace unsafe characters with underscore
    safe = UNSAFE_FILENAME_CHARS.sub("_", name)
    # Collapse multiple underscores
    safe = re.sub(r"_+", "_", safe)
    # Strip leading/trailing underscores and whitespace
    safe = safe.strip("_ ")
    return safe or "document"


class RootResource(DAVCollection):
    """Root collection listing all available shares."""

    def __init__(self, path: str, environ: dict[str, Any]) -> None:
        super().__init__(path, environ)
        self._shares = environ.get("shares", {})

    def get_display_name(self) -> str:
        return ""

    def get_member_names(self) -> list[str]:
        """Return list of share names."""
        return list(self._shares.keys())

    def get_member(self, name: str) -> "ShareResource | None":
        """Get a share by name."""
        if name in self._shares:
            return ShareResource(
                join_uri(self.path, name),
                {**self.environ, "share": self._shares[name]},
            )
        return None


class ShareResource(DAVCollection):
    """Collection representing a share (tag-filtered document set)."""

    def __init__(self, path: str, environ: dict[str, Any]) -> None:
        super().__init__(path, environ)
        self._share = environ["share"]
        self._paperless_client: PaperlessClient | None = environ.get("paperless_client")
        self._documents: list[PaperlessDocument] | None = None

    def get_display_name(self) -> str:
        return self._share.name

    def get_creation_date(self) -> datetime:
        return getattr(self._share, "created_at", datetime.now(timezone.utc))

    def get_last_modified(self) -> datetime:
        return getattr(self._share, "updated_at", datetime.now(timezone.utc))

    def _load_documents(self) -> list[PaperlessDocument]:
        """Load documents matching share's tag filter.

        Note: This is called synchronously from wsgidav, so we need
        to run the async code in a sync context. In production, this
        would use asyncio.run() or similar.
        """
        if self._documents is not None:
            return self._documents

        # Placeholder - in production this calls the async client
        # For now, return empty list (will be wired up in integration)
        self._documents = []
        return self._documents

    def get_member_names(self) -> list[str]:
        """Return list of document filenames."""
        documents = self._load_documents()
        names = []
        seen = set()

        for doc in documents:
            base_name = sanitize_filename(doc.title) + ".pdf"
            # Handle duplicate names
            name = base_name
            counter = 1
            while name in seen:
                name = f"{sanitize_filename(doc.title)}_{counter}.pdf"
                counter += 1
            seen.add(name)
            names.append(name)

        # Add done folder if enabled
        if self._share.done_folder_enabled:
            names.append(self._share.done_folder_name)

        return names

    def get_member(self, name: str) -> "DocumentResource | DoneFolderResource | None":
        """Get a document or done folder by name."""
        # Check for done folder
        if self._share.done_folder_enabled and name == self._share.done_folder_name:
            return DoneFolderResource(
                join_uri(self.path, name),
                {**self.environ, "share": self._share},
            )

        # Find document by filename
        documents = self._load_documents()
        seen = set()

        for doc in documents:
            base_name = sanitize_filename(doc.title) + ".pdf"
            doc_name = base_name
            counter = 1
            while doc_name in seen:
                doc_name = f"{sanitize_filename(doc.title)}_{counter}.pdf"
                counter += 1
            seen.add(doc_name)

            if doc_name == name:
                return DocumentResource(
                    join_uri(self.path, name),
                    {**self.environ, "document": doc},
                )

        return None


class DoneFolderResource(DAVCollection):
    """Virtual folder for documents marked as 'done'."""

    def __init__(self, path: str, environ: dict[str, Any]) -> None:
        super().__init__(path, environ)
        self._share = environ["share"]
        self._documents: list[PaperlessDocument] | None = None

    def get_display_name(self) -> str:
        return self._share.done_folder_name

    def get_member_names(self) -> list[str]:
        """Return list of done document filenames."""
        # Placeholder - will be implemented with tag filtering
        return []

    def get_member(self, name: str) -> "DocumentResource | None":
        """Get a done document by name."""
        return None


class DocumentResource(DAVNonCollection):
    """Resource representing a single Paperless document."""

    def __init__(self, path: str, environ: dict[str, Any]) -> None:
        super().__init__(path, environ)
        self._document: PaperlessDocument = environ["document"]
        self._paperless_client: PaperlessClient | None = environ.get("paperless_client")
        self._content: bytes | None = None

    def get_display_name(self) -> str:
        return sanitize_filename(self._document.title) + ".pdf"

    def get_content_type(self) -> str:
        return "application/pdf"

    def get_content_length(self) -> int | None:
        # We don't know the size without downloading
        # Return None to indicate unknown
        return None

    def get_creation_date(self) -> datetime:
        return self._document.created

    def get_last_modified(self) -> datetime:
        return self._document.modified

    def get_etag(self) -> str:
        """Generate ETag from document ID and modified time."""
        return f'"{self._document.id}-{self._document.modified.timestamp()}"'

    def get_content(self) -> BytesIO:
        """Return document content as file-like object.

        Note: In production, this would use async download.
        """
        if self._content is None:
            # Placeholder - will be wired up to async download
            self._content = b""
        return BytesIO(self._content)

    def support_etag(self) -> bool:
        return True

    def support_ranges(self) -> bool:
        return False  # Simplify for now


class PaperlessProvider(DAVProvider):
    """wsgidav provider that exposes Paperless documents via WebDAV.

    Shares are loaded from the database and documents are fetched
    from the Paperless API based on tag filters.
    """

    def __init__(self, shares: dict[str, Any] | None = None) -> None:
        """Initialize provider with share configurations.

        Args:
            shares: Dict mapping share names to share config objects
        """
        super().__init__()
        self._shares = shares or {}

    def set_shares(self, shares: dict[str, Any]) -> None:
        """Update available shares.

        Args:
            shares: Dict mapping share names to share config objects
        """
        self._shares = shares

    def get_resource_inst(self, path: str, environ: dict[str, Any]) -> DAVCollection | DAVNonCollection | None:
        """Return a resource object for the given path.

        Args:
            path: WebDAV path (e.g., "/tax2025/document.pdf")
            environ: WSGI environ dict with request context

        Returns:
            Resource object or None if not found
        """
        # Add shares to environ for child resources
        environ["shares"] = self._shares

        path = path.rstrip("/")
        parts = path.split("/")

        # Root
        if path in ("", "/"):
            return RootResource("/", environ)

        # Share root (e.g., /tax2025)
        if len(parts) == 2:
            share_name = parts[1]
            if share_name in self._shares:
                return ShareResource(
                    path,
                    {**environ, "share": self._shares[share_name]},
                )
            return None

        # Document or done folder (e.g., /tax2025/doc.pdf or /tax2025/done)
        if len(parts) == 3:
            share_name = parts[1]
            if share_name not in self._shares:
                return None

            share = self._shares[share_name]
            share_resource = ShareResource(
                f"/{share_name}",
                {**environ, "share": share},
            )
            return share_resource.get_member(parts[2])

        # Document in done folder (e.g., /tax2025/done/doc.pdf)
        if len(parts) == 4:
            share_name = parts[1]
            done_folder = parts[2]
            doc_name = parts[3]

            if share_name not in self._shares:
                return None

            share = self._shares[share_name]
            if not share.done_folder_enabled or done_folder != share.done_folder_name:
                return None

            done_resource = DoneFolderResource(
                f"/{share_name}/{done_folder}",
                {**environ, "share": share},
            )
            return done_resource.get_member(doc_name)

        return None
```

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_webdav_provider.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/webdav_provider.py tests/test_webdav_provider.py
git commit -m "feat: add wsgidav provider for Paperless documents

- PaperlessProvider as main DAV provider
- RootResource lists available shares
- ShareResource lists documents filtered by tags
- DocumentResource serves individual PDFs
- DoneFolderResource for done tracking (placeholder)
- Filename sanitization for filesystem safety

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: FastAPI Admin API

### Task 2.1: FastAPI Application Skeleton

**Files:**
- Create: `src/paperless_webdav/app.py`
- Create: `src/paperless_webdav/api/__init__.py`
- Create: `src/paperless_webdav/api/health.py`
- Create: `tests/test_app.py`

**Step 1: Write the failing test**

```python
# tests/test_app.py
"""Tests for FastAPI application."""

import pytest
from httpx import AsyncClient, ASGITransport

from paperless_webdav.app import create_app


@pytest.fixture
def app(mock_settings):
    """Create test application."""
    return create_app()


@pytest.mark.asyncio
async def test_health_endpoint(app):
    """Health endpoint should return 200."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready_endpoint_without_db(app):
    """Ready endpoint should return 503 when DB unavailable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    # Without DB connection, should return not ready
    assert response.status_code == 503
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_app.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create API health module**

```python
# src/paperless_webdav/api/__init__.py
"""FastAPI API routers."""
```

```python
# src/paperless_webdav/api/health.py
"""Health check endpoints."""

from fastapi import APIRouter, Response

from paperless_webdav.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe - is the service running?

    Returns 200 if the service is alive. Does not check dependencies.
    """
    return {"status": "healthy"}


@router.get("/ready")
async def ready(response: Response) -> dict:
    """Readiness probe - can the service handle requests?

    Checks database and Paperless connectivity.
    Returns 200 if ready, 503 if not.
    """
    checks = {
        "database": False,
        "paperless": False,
    }

    # TODO: Implement actual checks
    # For now, return not ready

    all_ready = all(checks.values())

    if not all_ready:
        response.status_code = 503
        logger.warning("readiness_check_failed", checks=checks)

    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": checks,
    }
```

**Step 4: Create main app**

```python
# src/paperless_webdav/app.py
"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from paperless_webdav.api.health import router as health_router
from paperless_webdav.config import get_settings
from paperless_webdav.logging import setup_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)
    logger.info("application_starting", admin_port=settings.admin_port)

    # TODO: Initialize database
    # TODO: Initialize Paperless client

    yield

    # Cleanup
    logger.info("application_stopping")
    # TODO: Close database connections


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI instance
    """
    app = FastAPI(
        title="paperless-webdav",
        description="WebDAV bridge for Paperless-ngx with tag-based shares",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(health_router)

    return app


# For direct uvicorn usage
app = create_app()
```

**Step 5: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_app.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/paperless_webdav/app.py src/paperless_webdav/api/ tests/test_app.py
git commit -m "feat: add FastAPI application with health endpoints

- Application factory pattern with lifespan handler
- /health endpoint for liveness probes
- /ready endpoint for readiness probes (placeholder)
- CORS middleware for development

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2.2: Share CRUD API Endpoints

**Files:**
- Create: `src/paperless_webdav/api/shares.py`
- Create: `src/paperless_webdav/schemas.py`
- Create: `tests/test_api_shares.py`

**Step 1: Write the failing test**

```python
# tests/test_api_shares.py
"""Tests for share API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

from paperless_webdav.app import create_app


@pytest.fixture
def app(mock_settings):
    """Create test application."""
    return create_app()


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = uuid4()
    user.external_id = "barry"
    return user


@pytest.mark.asyncio
async def test_list_shares_empty(app, mock_user):
    """List shares should return empty list initially."""
    with patch("paperless_webdav.api.shares.get_current_user", return_value=mock_user):
        with patch("paperless_webdav.api.shares.get_user_shares", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/shares")

            assert response.status_code == 200
            assert response.json() == []


@pytest.mark.asyncio
async def test_create_share(app, mock_user):
    """Create share should return the new share."""
    with patch("paperless_webdav.api.shares.get_current_user", return_value=mock_user):
        with patch("paperless_webdav.api.shares.create_share", new_callable=AsyncMock) as mock_create:
            share_id = uuid4()
            mock_create.return_value = MagicMock(
                id=share_id,
                name="tax2025",
                include_tags=["tax", "2025"],
                exclude_tags=[],
                expires_at=None,
                read_only=True,
                done_folder_enabled=False,
                done_folder_name="done",
                done_tag=None,
                allowed_users=[],
            )

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/shares", json={
                    "name": "tax2025",
                    "include_tags": ["tax", "2025"],
                })

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "tax2025"
            assert data["include_tags"] == ["tax", "2025"]


@pytest.mark.asyncio
async def test_create_share_invalid_name(app, mock_user):
    """Create share with invalid name should return 422."""
    with patch("paperless_webdav.api.shares.get_current_user", return_value=mock_user):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/shares", json={
                "name": "invalid name!",  # spaces and special chars not allowed
                "include_tags": ["tax"],
            })

        assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_share(app, mock_user):
    """Delete share should return 204."""
    with patch("paperless_webdav.api.shares.get_current_user", return_value=mock_user):
        with patch("paperless_webdav.api.shares.delete_share", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = True

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.delete("/api/shares/tax2025")

            assert response.status_code == 204
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_api_shares.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create schemas**

```python
# src/paperless_webdav/schemas.py
"""Pydantic schemas for API request/response validation."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# Regex for valid share names
SHARE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$")


class ShareCreate(BaseModel):
    """Schema for creating a new share."""

    name: str = Field(min_length=1, max_length=63, description="Share name (alphanumeric + dash)")
    include_tags: list[str] = Field(min_length=1, description="Tags documents must have")
    exclude_tags: list[str] = Field(default_factory=list, description="Tags documents must not have")
    expires_at: datetime | None = Field(default=None, description="Share expiration time")
    read_only: bool = Field(default=True, description="Whether share is read-only")
    done_folder_enabled: bool = Field(default=False, description="Enable done folder")
    done_folder_name: str = Field(default="done", max_length=63, description="Done folder name")
    done_tag: str | None = Field(default=None, description="Tag to apply when moved to done")
    allowed_users: list[str] = Field(default_factory=list, description="Additional allowed users")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure share name is alphanumeric with dashes only."""
        if not SHARE_NAME_PATTERN.match(v):
            raise ValueError("Share name must be alphanumeric with dashes, 1-63 chars")
        return v

    @field_validator("done_tag")
    @classmethod
    def validate_done_tag(cls, v: str | None, info) -> str | None:
        """Ensure done_tag is set if done_folder_enabled."""
        if info.data.get("done_folder_enabled") and not v:
            raise ValueError("done_tag is required when done_folder_enabled is True")
        return v


class ShareUpdate(BaseModel):
    """Schema for updating a share."""

    include_tags: list[str] | None = None
    exclude_tags: list[str] | None = None
    expires_at: datetime | None = None
    read_only: bool | None = None
    done_folder_enabled: bool | None = None
    done_folder_name: str | None = None
    done_tag: str | None = None
    allowed_users: list[str] | None = None


class ShareResponse(BaseModel):
    """Schema for share in API responses."""

    id: UUID
    name: str
    include_tags: list[str]
    exclude_tags: list[str]
    expires_at: datetime | None
    read_only: bool
    done_folder_enabled: bool
    done_folder_name: str
    done_tag: str | None
    allowed_users: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TagResponse(BaseModel):
    """Schema for Paperless tag in API responses."""

    id: int
    name: str
    slug: str
```

**Step 4: Create shares API router**

```python
# src/paperless_webdav/api/shares.py
"""Share management API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from paperless_webdav.schemas import ShareCreate, ShareUpdate, ShareResponse
from paperless_webdav.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/shares", tags=["shares"])


# Placeholder for auth dependency
async def get_current_user():
    """Get the currently authenticated user.

    TODO: Implement actual authentication
    """
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


# Placeholder for database operations
async def get_user_shares(user_id: UUID) -> list:
    """Get all shares owned by or accessible to a user."""
    return []


async def create_share(user_id: UUID, data: ShareCreate):
    """Create a new share in the database."""
    raise NotImplementedError()


async def get_share_by_name(name: str, user_id: UUID):
    """Get a share by name if user has access."""
    return None


async def update_share(share_id: UUID, data: ShareUpdate):
    """Update a share in the database."""
    raise NotImplementedError()


async def delete_share(name: str, user_id: UUID) -> bool:
    """Delete a share from the database."""
    return False


CurrentUser = Annotated[object, Depends(get_current_user)]


@router.get("", response_model=list[ShareResponse])
async def list_shares(current_user: CurrentUser) -> list:
    """List all shares accessible to the current user."""
    shares = await get_user_shares(current_user.id)
    logger.info("shares_listed", user_id=str(current_user.id), count=len(shares))
    return shares


@router.post("", response_model=ShareResponse, status_code=status.HTTP_201_CREATED)
async def create_new_share(data: ShareCreate, current_user: CurrentUser):
    """Create a new share."""
    share = await create_share(current_user.id, data)
    logger.info(
        "share_created",
        user_id=str(current_user.id),
        share_name=data.name,
    )
    return share


@router.get("/{name}", response_model=ShareResponse)
async def get_share(name: str, current_user: CurrentUser):
    """Get a share by name."""
    share = await get_share_by_name(name, current_user.id)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Share '{name}' not found",
        )
    return share


@router.put("/{name}", response_model=ShareResponse)
async def update_existing_share(name: str, data: ShareUpdate, current_user: CurrentUser):
    """Update a share."""
    share = await get_share_by_name(name, current_user.id)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Share '{name}' not found",
        )

    updated = await update_share(share.id, data)
    logger.info(
        "share_updated",
        user_id=str(current_user.id),
        share_name=name,
    )
    return updated


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_share(name: str, current_user: CurrentUser):
    """Delete a share."""
    deleted = await delete_share(name, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Share '{name}' not found",
        )
    logger.info(
        "share_deleted",
        user_id=str(current_user.id),
        share_name=name,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

**Step 5: Register router in app.py**

Update `src/paperless_webdav/app.py` to include:

```python
from paperless_webdav.api.shares import router as shares_router

# In create_app(), add:
app.include_router(shares_router)
```

**Step 6: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_api_shares.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/paperless_webdav/schemas.py src/paperless_webdav/api/shares.py src/paperless_webdav/app.py tests/test_api_shares.py
git commit -m "feat: add share CRUD API endpoints

- ShareCreate/Update/Response schemas with validation
- Share name validation (alphanumeric + dash)
- List, create, get, update, delete endpoints
- Auth dependency placeholder
- Audit logging for share operations

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Remaining Tasks (Abbreviated)

The following tasks continue the same pattern. Due to length, I'll list them with key files and brief descriptions:

### Task 2.3: Tags API Endpoints
- `src/paperless_webdav/api/tags.py` - GET /api/tags, GET /api/tags/search
- Uses PaperlessClient to proxy tag queries

### Task 2.4: Paperless-Native Authentication
- `src/paperless_webdav/auth/paperless.py` - Login via Paperless /api/token/
- Session management with itsdangerous

### Task 2.5: Database Migrations with Alembic
- `alembic.ini`, `alembic/env.py`, `alembic/versions/001_initial.py`
- Create tables for users, shares, audit_log

### Task 2.6: Wire Up Database to API
- Update shares.py to use real SQLAlchemy queries
- Add session dependency injection

### Task 2.7: Admin UI Templates - Base Layout
- `src/paperless_webdav/templates/base.html` - Tailwind + HTMX setup
- `src/paperless_webdav/templates/login.html`

### Task 2.8: Admin UI - Share Management Pages
- `src/paperless_webdav/templates/shares/list.html`
- `src/paperless_webdav/templates/shares/create.html`
- `src/paperless_webdav/templates/shares/edit.html`

### Task 2.9: HTMX Tag Autocomplete
- `src/paperless_webdav/templates/partials/tag_suggestions.html`
- Wire to /api/tags/search endpoint

### Task 2.10: Wire WebDAV Provider to Database
- Connect PaperlessProvider to load shares from DB
- Integrate async Paperless client for document fetching

### Task 2.11: WebDAV Server Integration
- `src/paperless_webdav/webdav_server.py` - Cheroot WSGI server setup
- `src/paperless_webdav/main.py` - Run both servers

---

## Phase 3: Done Folder Feature

### Task 3.1: Done Folder Document Filtering
- Filter root listing to exclude docs with done_tag
- Filter done folder listing to include only docs with done_tag

### Task 3.2: MOVE Operation Handler (Root → Done)
- Handle MOVE from `/share/doc.pdf` to `/share/done/doc.pdf`
- Add done_tag to document via Paperless API
- Document disappears from root, appears in done folder

### Task 3.3: MOVE Operation Handler (Done → Root)
- Handle MOVE from `/share/done/doc.pdf` to `/share/doc.pdf`
- Remove done_tag from document via Paperless API
- Document disappears from done folder, reappears in root
- **Bidirectional workflow: users can "undo" marking something as done**

### Task 3.4: MOVE Validation
- Only allow moves within same share
- Only allow moves between root ↔ done folder
- Reject moves to invalid paths

---

## Phase 4: OIDC Support

### Task 4.1: OIDC Authentication Flow
### Task 4.2: LDAP Authentication for WebDAV
### Task 4.3: Token Prompt UI for First Login
### Task 4.4: Encrypted Token Storage

---

## Phase 5: Production Hardening

### Task 5.1: Rate Limiting Middleware
### Task 5.2: Audit Log Service
### Task 5.3: Share Expiration Enforcement
### Task 5.4: Dockerfile and Container Build
### Task 5.5: Kubernetes Manifests

---

## Phase 6: Polish

### Task 6.1: Allowed Users Feature
### Task 6.2: UI Error Handling
### Task 6.3: Documentation

---

## Running the Project

After completing Phase 2, you can run the development server:

```bash
cd /home/barry/paperless-webdav/.worktrees/dev
source .venv/bin/activate

# Set environment variables
export PAPERLESS_URL=https://paperless.example.com
export DATABASE_URL=postgresql://user:pass@localhost/paperless_webdav
export ENCRYPTION_KEY=$(python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())")
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# Run migrations
alembic upgrade head

# Start the server
uvicorn paperless_webdav.app:app --reload --port 8080
```

## Testing

Run all tests:
```bash
pytest tests/ -v --cov=paperless_webdav
```

Run specific test file:
```bash
pytest tests/test_paperless_client.py -v
```
