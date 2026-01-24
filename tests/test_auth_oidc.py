# tests/test_auth_oidc.py
"""Tests for OIDC authentication routes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport

from paperless_webdav.app import create_app


@pytest.fixture
def mock_oidc_settings():
    """Provide test settings with OIDC enabled."""
    with patch.dict("os.environ", {
        "PAPERLESS_URL": "http://paperless.test",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "ENCRYPTION_KEY": "dGVzdGtleXRoYXRpczMyYnl0ZXNsb25nIQ==",
        "SECRET_KEY": "test-secret-key-for-sessions",
        "AUTH_MODE": "oidc",
        "OIDC_ISSUER": "https://authentik.example.com/application/o/paperless",
        "OIDC_CLIENT_ID": "test-client-id",
        "OIDC_CLIENT_SECRET": "test-client-secret",
    }):
        yield


@pytest.fixture
def mock_paperless_settings():
    """Provide test settings with Paperless auth mode (default)."""
    with patch.dict("os.environ", {
        "PAPERLESS_URL": "http://paperless.test",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "ENCRYPTION_KEY": "dGVzdGtleXRoYXRpczMyYnl0ZXNsb25nIQ==",
        "SECRET_KEY": "test-secret-key-for-sessions",
        "AUTH_MODE": "paperless",
    }):
        yield


@pytest.fixture
def oidc_app(mock_oidc_settings):
    """Create test application with OIDC enabled."""
    # Clear cached settings and OAuth client
    from paperless_webdav.config import get_settings
    from paperless_webdav.auth import oidc
    get_settings.cache_clear()
    oidc._oauth = None
    return create_app()


@pytest.fixture
def paperless_app(mock_paperless_settings):
    """Create test application with Paperless auth mode."""
    from paperless_webdav.config import get_settings
    from paperless_webdav.auth import oidc
    get_settings.cache_clear()
    oidc._oauth = None
    return create_app()


class TestOidcLogin:
    """Tests for the /auth/login OIDC route."""

    @pytest.mark.asyncio
    async def test_oidc_login_redirects_to_provider(self, oidc_app):
        """GET /auth/login in OIDC mode should redirect to OIDC provider."""
        # Mock the OAuth client's authorize_redirect
        mock_redirect_response = MagicMock()
        mock_redirect_response.status_code = 302
        mock_redirect_response.headers = {"location": "https://authentik.example.com/authorize"}

        with patch("paperless_webdav.auth.oidc.get_oauth") as mock_get_oauth:
            mock_oauth = MagicMock()
            mock_oauth.authentik.authorize_redirect = AsyncMock(return_value=mock_redirect_response)
            mock_get_oauth.return_value = mock_oauth

            async with AsyncClient(
                transport=ASGITransport(app=oidc_app), base_url="http://test"
            ) as client:
                # Don't follow redirects so we can inspect the redirect response
                response = await client.get("/auth/login", follow_redirects=False)

        # Should have called authorize_redirect
        mock_oauth.authentik.authorize_redirect.assert_called_once()

    @pytest.mark.asyncio
    async def test_oidc_login_in_paperless_mode_redirects_to_ui_login(self, paperless_app):
        """GET /auth/login in paperless mode should redirect to /ui/login."""
        async with AsyncClient(
            transport=ASGITransport(app=paperless_app), base_url="http://test"
        ) as client:
            response = await client.get("/auth/login", follow_redirects=False)

        assert response.status_code == 307  # Temporary redirect
        assert response.headers["location"] == "/ui/login"


class TestOidcCallback:
    """Tests for the /auth/callback OIDC route."""

    @pytest.mark.asyncio
    async def test_oidc_callback_creates_session(self, oidc_app):
        """OIDC callback should create session with user info."""
        # Mock token response with userinfo
        mock_token = {
            "access_token": "test-access-token",
            "userinfo": {
                "sub": "user123",
                "preferred_username": "testuser",
                "email": "testuser@example.com",
            },
        }

        with patch("paperless_webdav.auth.oidc.get_oauth") as mock_get_oauth:
            mock_oauth = MagicMock()
            mock_oauth.authentik.authorize_access_token = AsyncMock(return_value=mock_token)
            mock_get_oauth.return_value = mock_oauth

            async with AsyncClient(
                transport=ASGITransport(app=oidc_app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/auth/callback?code=auth-code&state=test-state",
                    follow_redirects=False,
                )

        # Should redirect to token-setup page
        assert response.status_code == 307
        assert response.headers["location"] == "/ui/token-setup"

        # Should set session cookie
        assert "session" in response.cookies
        assert len(response.cookies["session"]) > 0

    @pytest.mark.asyncio
    async def test_oidc_callback_uses_sub_if_no_preferred_username(self, oidc_app):
        """OIDC callback should use sub claim if preferred_username not present."""
        mock_token = {
            "access_token": "test-access-token",
            "userinfo": {
                "sub": "user123",
                "email": "testuser@example.com",
            },
        }

        with patch("paperless_webdav.auth.oidc.get_oauth") as mock_get_oauth:
            mock_oauth = MagicMock()
            mock_oauth.authentik.authorize_access_token = AsyncMock(return_value=mock_token)
            mock_get_oauth.return_value = mock_oauth

            async with AsyncClient(
                transport=ASGITransport(app=oidc_app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/auth/callback?code=auth-code&state=test-state",
                    follow_redirects=False,
                )

        # Should still succeed with sub as username
        assert response.status_code == 307
        assert response.headers["location"] == "/ui/token-setup"
        assert "session" in response.cookies

    @pytest.mark.asyncio
    async def test_oidc_callback_error_redirects_to_login(self, oidc_app):
        """OIDC callback error should redirect to login with error."""
        with patch("paperless_webdav.auth.oidc.get_oauth") as mock_get_oauth:
            mock_oauth = MagicMock()
            mock_oauth.authentik.authorize_access_token = AsyncMock(
                side_effect=Exception("Token exchange failed")
            )
            mock_get_oauth.return_value = mock_oauth

            async with AsyncClient(
                transport=ASGITransport(app=oidc_app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/auth/callback?code=invalid-code&state=test-state",
                    follow_redirects=False,
                )

        assert response.status_code == 307
        assert "/ui/login" in response.headers["location"]
        assert "error=auth_failed" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oidc_callback_no_username_redirects_to_login(self, oidc_app):
        """OIDC callback without username should redirect to login with error."""
        mock_token = {
            "access_token": "test-access-token",
            "userinfo": {
                # No sub or preferred_username
                "email": "testuser@example.com",
            },
        }

        with patch("paperless_webdav.auth.oidc.get_oauth") as mock_get_oauth:
            mock_oauth = MagicMock()
            mock_oauth.authentik.authorize_access_token = AsyncMock(return_value=mock_token)
            mock_get_oauth.return_value = mock_oauth

            async with AsyncClient(
                transport=ASGITransport(app=oidc_app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/auth/callback?code=auth-code&state=test-state",
                    follow_redirects=False,
                )

        assert response.status_code == 307
        assert "/ui/login" in response.headers["location"]
        assert "error=no_username" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oidc_callback_session_has_empty_token(self, oidc_app):
        """OIDC callback session should have empty Paperless token initially."""
        mock_token = {
            "access_token": "test-access-token",
            "userinfo": {
                "sub": "user123",
                "preferred_username": "testuser",
            },
        }

        with patch("paperless_webdav.auth.oidc.get_oauth") as mock_get_oauth:
            mock_oauth = MagicMock()
            mock_oauth.authentik.authorize_access_token = AsyncMock(return_value=mock_token)
            mock_get_oauth.return_value = mock_oauth

            async with AsyncClient(
                transport=ASGITransport(app=oidc_app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/auth/callback?code=auth-code&state=test-state",
                    follow_redirects=False,
                )

        # Verify session was created
        session_cookie = response.cookies.get("session")
        assert session_cookie is not None

        # Decode the session to verify it has empty token
        from paperless_webdav.auth.paperless import _validate_session
        from paperless_webdav.config import get_settings

        get_settings.cache_clear()
        settings = get_settings()
        user = _validate_session(session_cookie, settings)

        assert user is not None
        assert user.username == "testuser"
        assert user.token == ""  # Empty Paperless token


class TestGetOauth:
    """Tests for the get_oauth helper function."""

    def test_get_oauth_registers_client(self, mock_oidc_settings):
        """get_oauth should register the authentik client."""
        from paperless_webdav.config import get_settings
        from paperless_webdav.auth.oidc import get_oauth, _oauth

        # Clear any existing oauth
        import paperless_webdav.auth.oidc as oidc_module
        oidc_module._oauth = None

        get_settings.cache_clear()
        settings = get_settings()

        oauth = get_oauth(settings)

        # Should have registered authentik client
        assert oauth is not None
        # The client should be accessible
        assert hasattr(oauth, "authentik") or "authentik" in oauth._clients

    def test_get_oauth_returns_cached_instance(self, mock_oidc_settings):
        """get_oauth should return the same OAuth instance on subsequent calls."""
        from paperless_webdav.config import get_settings
        from paperless_webdav.auth.oidc import get_oauth

        import paperless_webdav.auth.oidc as oidc_module
        oidc_module._oauth = None

        get_settings.cache_clear()
        settings = get_settings()

        oauth1 = get_oauth(settings)
        oauth2 = get_oauth(settings)

        assert oauth1 is oauth2
