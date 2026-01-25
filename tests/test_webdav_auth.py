# tests/test_webdav_auth.py
"""Tests for WebDAV HTTP Basic authentication."""

import pytest
from unittest.mock import patch

from paperless_webdav.webdav_auth import PaperlessBasicAuthenticator


@pytest.fixture
def authenticator(mock_settings):
    """Create authenticator instance."""
    return PaperlessBasicAuthenticator("http://paperless.test")


class TestBasicAuthUser:
    """Tests for basic_auth_user method."""

    def test_returns_username_on_valid_credentials(self, authenticator):
        """Valid credentials should return username."""
        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            mock_run.return_value = ("test-token-123", None)
            environ = {}

            result = authenticator.basic_auth_user("realm", "barry", "secret", environ)

            assert result == "barry"

    def test_stores_token_in_environ_on_success(self, authenticator):
        """Token should be stored in environ on successful auth."""
        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            mock_run.return_value = ("test-token-123", None)
            environ = {}

            authenticator.basic_auth_user("realm", "barry", "secret", environ)

            assert environ["paperless.token"] == "test-token-123"

    def test_stores_username_in_environ_on_success(self, authenticator):
        """Username should be stored in environ on successful auth."""
        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            mock_run.return_value = ("test-token-123", None)
            environ = {}

            authenticator.basic_auth_user("realm", "barry", "secret", environ)

            assert environ["paperless.username"] == "barry"

    def test_returns_false_on_invalid_credentials(self, authenticator):
        """Invalid credentials should return False."""
        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            mock_run.return_value = (None, "Invalid credentials")

            result = authenticator.basic_auth_user("realm", "barry", "wrong", {})

            assert result is False

    def test_does_not_store_token_on_failure(self, authenticator):
        """Token should not be stored in environ on failed auth."""
        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            mock_run.return_value = (None, "Invalid credentials")
            environ = {}

            authenticator.basic_auth_user("realm", "barry", "wrong", environ)

            assert "paperless.token" not in environ

    def test_calls_authenticate_with_paperless(self, authenticator):
        """Should call _authenticate_with_paperless via run_async."""
        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            mock_run.return_value = ("test-token-123", None)

            authenticator.basic_auth_user("realm", "barry", "secret", {})

            # Verify run_async was called
            mock_run.assert_called_once()
            # The argument should be a coroutine from _authenticate_with_paperless
            call_args = mock_run.call_args[0][0]
            assert call_args is not None


class TestTokenStorage:
    """Tests for internal token storage."""

    def test_stores_token_for_user(self, authenticator):
        """Authenticator should store token for later retrieval."""
        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            mock_run.return_value = ("test-token-123", None)

            authenticator.basic_auth_user("realm", "barry", "secret", {})

            assert authenticator.get_token("barry") == "test-token-123"

    def test_get_token_returns_none_for_unknown_user(self, authenticator):
        """get_token should return None for unknown users."""
        assert authenticator.get_token("unknown") is None

    def test_stores_multiple_user_tokens(self, authenticator):
        """Should store tokens for multiple users."""
        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            mock_run.return_value = ("token-barry", None)
            authenticator.basic_auth_user("realm", "barry", "secret", {})

            mock_run.return_value = ("token-alice", None)
            authenticator.basic_auth_user("realm", "alice", "password", {})

            assert authenticator.get_token("barry") == "token-barry"
            assert authenticator.get_token("alice") == "token-alice"


class TestWsgidavInterface:
    """Tests for wsgidav domain controller interface compliance."""

    def test_has_basic_auth_user_method(self, authenticator):
        """Authenticator should have basic_auth_user method."""
        assert hasattr(authenticator, "basic_auth_user")
        assert callable(authenticator.basic_auth_user)

    def test_supports_http_digest_auth_returns_false(self, authenticator):
        """supports_http_digest_auth should return False."""
        assert authenticator.supports_http_digest_auth() is False

    def test_require_authentication_returns_true(self, authenticator):
        """require_authentication should return True."""
        assert authenticator.require_authentication("realm", {}) is True

    def test_require_authentication_with_none_environ(self, authenticator):
        """require_authentication should handle None environ (startup check)."""
        assert authenticator.require_authentication("realm", None) is True

    def test_get_domain_realm_returns_realm_string(self, authenticator):
        """get_domain_realm should return realm string."""
        result = authenticator.get_domain_realm("/", {})
        assert result == "Paperless WebDAV"

    def test_get_domain_realm_with_none_environ(self, authenticator):
        """get_domain_realm should handle None environ (startup check)."""
        result = authenticator.get_domain_realm("/", None)
        assert result == "Paperless WebDAV"


class TestInitialization:
    """Tests for authenticator initialization."""

    def test_stores_paperless_url(self, mock_settings):
        """Authenticator should store the Paperless URL."""
        auth = PaperlessBasicAuthenticator("http://custom.test")
        assert auth._paperless_url == "http://custom.test"

    def test_initializes_empty_token_storage(self, mock_settings):
        """Authenticator should initialize with empty token storage."""
        auth = PaperlessBasicAuthenticator("http://paperless.test")
        assert auth._user_tokens == {}


class TestOIDCModeTokenLoading:
    """Tests for loading token from DB in OIDC mode."""

    def test_loads_token_from_db_in_oidc_mode(self, mock_oidc_settings):
        """In OIDC mode, authenticator should load token from DB using username as password."""
        from paperless_webdav.config import get_settings

        settings = get_settings()
        auth = PaperlessBasicAuthenticator(
            "http://paperless.test",
            auth_mode=settings.auth_mode,
            encryption_key=settings.encryption_key.get_secret_value(),
        )

        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            # Return token from DB lookup
            mock_run.return_value = "db-stored-token"
            environ = {}

            result = auth.basic_auth_user("realm", "barry", "barry", environ)

            assert result == "barry"
            assert environ["paperless.token"] == "db-stored-token"

    def test_oidc_mode_falls_back_to_paperless_auth_if_no_db_token(self, mock_oidc_settings):
        """In OIDC mode, if no DB token, should fall back to Paperless auth."""
        from paperless_webdav.config import get_settings

        settings = get_settings()
        auth = PaperlessBasicAuthenticator(
            "http://paperless.test",
            auth_mode=settings.auth_mode,
            encryption_key=settings.encryption_key.get_secret_value(),
        )

        call_count = 0

        def mock_run_impl(coro):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: DB lookup returns None
                return None
            else:
                # Second call: Paperless auth succeeds
                return ("paperless-token", None)

        with patch("paperless_webdav.webdav_auth.run_async", side_effect=mock_run_impl):
            environ = {}
            result = auth.basic_auth_user("realm", "barry", "secret", environ)

            assert result == "barry"
            assert environ["paperless.token"] == "paperless-token"

    def test_paperless_mode_does_not_check_db(self, mock_settings):
        """In paperless mode, should not attempt DB token lookup."""
        from paperless_webdav.config import get_settings

        settings = get_settings()
        auth = PaperlessBasicAuthenticator(
            "http://paperless.test",
            auth_mode=settings.auth_mode,
            encryption_key=settings.encryption_key.get_secret_value()
            if settings.encryption_key
            else None,
        )

        with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
            mock_run.return_value = ("paperless-token", None)
            environ = {}

            result = auth.basic_auth_user("realm", "barry", "secret", environ)

            assert result == "barry"
            # Should have called run_async exactly once for Paperless auth
            # (not for DB lookup first)
            assert mock_run.call_count == 1
