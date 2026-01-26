"""Shared test fixtures."""

import os

# Set test environment variables BEFORE any imports that trigger Settings validation.
# This is required because app.py creates the app at module import time.
os.environ.setdefault("PAPERLESS_URL", "http://paperless.test")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("ENCRYPTION_KEY", "aa8D7QnZUqkFGBniEyIfESXitQUijPhSjQZLIqltUy4=")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-sessions")

import pytest
from unittest.mock import patch

from paperless_webdav.cache import get_cache
from paperless_webdav.config import get_settings
from paperless_webdav import webdav_auth


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear all caches before and after each test to prevent pollution."""
    # Clear document cache
    cache = get_cache()
    try:
        cache.clear()
    except ValueError:
        # Ignore I/O errors from logging when stdout is captured/closed
        pass
    # Clear auth cache
    webdav_auth._auth_cache.clear()
    yield
    try:
        cache.clear()
    except ValueError:
        pass
    webdav_auth._auth_cache.clear()


@pytest.fixture
def mock_settings():
    """Provide test settings."""
    get_settings.cache_clear()
    with patch.dict(
        "os.environ",
        {
            "PAPERLESS_URL": "http://paperless.test",
            "DATABASE_URL": "postgresql://test:test@localhost/test",
            "ENCRYPTION_KEY": "aa8D7QnZUqkFGBniEyIfESXitQUijPhSjQZLIqltUy4=",
            "SECRET_KEY": "test-secret-key-for-sessions",
        },
    ):
        yield
    get_settings.cache_clear()


@pytest.fixture
def mock_oidc_settings():
    """Provide test settings with auth_mode=oidc."""
    get_settings.cache_clear()
    with patch.dict(
        "os.environ",
        {
            "PAPERLESS_URL": "http://paperless.test",
            "DATABASE_URL": "postgresql://test:test@localhost/test",
            "ENCRYPTION_KEY": "aa8D7QnZUqkFGBniEyIfESXitQUijPhSjQZLIqltUy4=",
            "SECRET_KEY": "test-secret-key-for-sessions",
            "AUTH_MODE": "oidc",
            "OIDC_ISSUER": "https://auth.example.com",
            "OIDC_CLIENT_ID": "test-client-id",
            "OIDC_CLIENT_SECRET": "test-client-secret",
        },
    ):
        yield
    get_settings.cache_clear()
