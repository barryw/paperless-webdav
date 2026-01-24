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
