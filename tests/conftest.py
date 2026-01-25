"""Shared test fixtures."""

import pytest
from unittest.mock import patch

from paperless_webdav.config import get_settings


@pytest.fixture
def mock_settings():
    """Provide test settings."""
    get_settings.cache_clear()
    with patch.dict(
        "os.environ",
        {
            "PAPERLESS_URL": "http://paperless.test",
            "DATABASE_URL": "postgresql://test:test@localhost/test",
            "ENCRYPTION_KEY": "dGVzdGtleXRoYXRpczMyYnl0ZXNsb25nIQ==",
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
            "ENCRYPTION_KEY": "dGVzdGtleXRoYXRpczMyYnl0ZXNsb25nIQ==",
            "SECRET_KEY": "test-secret-key-for-sessions",
            "AUTH_MODE": "oidc",
            "OIDC_ISSUER": "https://auth.example.com",
            "OIDC_CLIENT_ID": "test-client-id",
            "OIDC_CLIENT_SECRET": "test-client-secret",
        },
    ):
        yield
    get_settings.cache_clear()
