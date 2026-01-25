# tests/test_auth_paperless.py
"""Tests for Paperless-native authentication."""

import pytest
import respx
from httpx import AsyncClient, ASGITransport, Response
from unittest.mock import AsyncMock, MagicMock, patch

from paperless_webdav.app import create_app
from paperless_webdav.auth.paperless import (
    _create_session,
    _validate_session,
    get_current_user,
    get_current_user_optional,
)
from paperless_webdav.config import get_settings


@pytest.fixture
def app(mock_settings):
    """Create test application."""
    return create_app()


class TestLogin:
    """Tests for the login endpoint."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_login_success(self, app):
        """Successful login should set session cookie."""
        respx.post("http://paperless.test/api/token/").mock(
            return_value=Response(200, json={"token": "abc123"})
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "barry", "password": "secret"},
            )

        assert response.status_code == 200
        assert "session" in response.cookies
        data = response.json()
        assert data["username"] == "barry"

    @respx.mock
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, app):
        """Invalid credentials should return 401."""
        respx.post("http://paperless.test/api/token/").mock(
            return_value=Response(400, json={"non_field_errors": ["Unable to log in"]})
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "barry", "password": "wrong"},
            )

        assert response.status_code == 401
        assert "session" not in response.cookies

    @respx.mock
    @pytest.mark.asyncio
    async def test_login_paperless_unavailable(self, app):
        """Paperless server errors should return 502."""
        respx.post("http://paperless.test/api/token/").mock(return_value=Response(500))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "barry", "password": "secret"},
            )

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_login_missing_username(self, app):
        """Missing username should return 422."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"password": "secret"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_missing_password(self, app):
        """Missing password should return 422."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "barry"},
            )

        assert response.status_code == 422


class TestLogout:
    """Tests for the logout endpoint."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_logout_clears_session(self, app):
        """Logout should clear the session cookie."""
        # First login to get a session
        respx.post("http://paperless.test/api/token/").mock(
            return_value=Response(200, json={"token": "abc123"})
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Login first
            login_response = await client.post(
                "/api/auth/login",
                json={"username": "barry", "password": "secret"},
            )
            session_cookie = login_response.cookies.get("session")

            # Then logout
            response = await client.post(
                "/api/auth/logout",
                cookies={"session": session_cookie},
            )

        assert response.status_code == 200
        # Check that the response contains message
        assert response.json() == {"message": "Logged out"}
        # Check that set-cookie header clears the session
        set_cookie = response.headers.get("set-cookie", "")
        assert "session=" in set_cookie
        assert "Max-Age=0" in set_cookie

    @pytest.mark.asyncio
    async def test_logout_without_session(self, app):
        """Logout without session should still succeed."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/auth/logout")

        assert response.status_code == 200


class TestMe:
    """Tests for the /me endpoint."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_me_authenticated(self, app):
        """Authenticated user should get their info."""
        respx.post("http://paperless.test/api/token/").mock(
            return_value=Response(200, json={"token": "abc123"})
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Login first
            login_response = await client.post(
                "/api/auth/login",
                json={"username": "barry", "password": "secret"},
            )
            session_cookie = login_response.cookies.get("session")

            # Then get user info
            response = await client.get(
                "/api/auth/me",
                cookies={"session": session_cookie},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "barry"

    @pytest.mark.asyncio
    async def test_me_unauthenticated(self, app):
        """Unauthenticated request should return 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_invalid_session(self, app):
        """Invalid session should return 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                cookies={"session": "invalid-session-token"},
            )

        assert response.status_code == 401

    @respx.mock
    @pytest.mark.asyncio
    async def test_me_expired_session(self, app):
        """Expired session should return 401."""
        # This test relies on session expiry being configurable
        # For now, we test with a tampered/old session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/auth/me",
                cookies={"session": "tampered.session.token"},
            )

        assert response.status_code == 401


class TestSessionManagement:
    """Tests for session management with itsdangerous."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_session_contains_encrypted_token(self, app):
        """Session should contain the encrypted Paperless token."""
        respx.post("http://paperless.test/api/token/").mock(
            return_value=Response(200, json={"token": "abc123"})
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "barry", "password": "secret"},
            )

        # Session cookie should exist and be non-empty
        session_cookie = response.cookies.get("session")
        assert session_cookie is not None
        assert len(session_cookie) > 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_token_available_for_paperless_requests(self, app):
        """After login, the token should be usable for Paperless API requests."""
        # Login
        respx.post("http://paperless.test/api/token/").mock(
            return_value=Response(200, json={"token": "abc123"})
        )
        # Mock tags endpoint
        respx.get("http://paperless.test/api/tags/").mock(
            return_value=Response(
                200,
                json={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [{"id": 1, "name": "tax", "slug": "tax", "color": "#ff0000"}],
                },
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Login
            login_response = await client.post(
                "/api/auth/login",
                json={"username": "barry", "password": "secret"},
            )
            session_cookie = login_response.cookies.get("session")

            # Make authenticated request to tags
            response = await client.get(
                "/api/tags",
                cookies={"session": session_cookie},
            )

        assert response.status_code == 200
        assert len(response.json()) == 1


class TestTokenLoadingFromDB:
    """Tests for loading Paperless token from database for OIDC users."""

    @pytest.mark.asyncio
    async def test_get_current_user_loads_token_from_db_if_missing(self, mock_oidc_settings):
        """get_current_user should load token from DB for OIDC users with empty session token."""
        settings = get_settings()

        # Create session with username but empty token (OIDC user post-login)
        session_value = _create_session("barry", "", settings)

        # Mock get_user_token to return stored token from DB
        with patch(
            "paperless_webdav.auth.paperless.get_user_token", new_callable=AsyncMock
        ) as mock_get_token:
            mock_get_token.return_value = "db-stored-token"

            # Mock get_session to provide a database session
            mock_db_session = MagicMock()
            with patch("paperless_webdav.auth.paperless.get_session") as mock_get_session:

                async def async_gen():
                    yield mock_db_session

                mock_get_session.return_value = async_gen()

                user = await get_current_user(session=session_value, settings=settings)

        assert user.username == "barry"
        assert user.token == "db-stored-token"
        mock_get_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_user_returns_none_if_no_token_in_db(self, mock_oidc_settings):
        """get_current_user should return None/raise 401 if no token in session or DB."""
        settings = get_settings()

        # Create session with username but empty token
        session_value = _create_session("barry", "", settings)

        # Mock get_user_token to return None (no token stored)
        with patch(
            "paperless_webdav.auth.paperless.get_user_token", new_callable=AsyncMock
        ) as mock_get_token:
            mock_get_token.return_value = None

            # Mock get_session to provide a database session
            mock_db_session = MagicMock()
            with patch("paperless_webdav.auth.paperless.get_session") as mock_get_session:

                async def async_gen():
                    yield mock_db_session

                mock_get_session.return_value = async_gen()

                # get_current_user_optional should return None
                user = await get_current_user_optional(session=session_value, settings=settings)

        assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_uses_session_token_if_present(self, mock_settings):
        """get_current_user should use session token if present (not load from DB)."""
        settings = get_settings()

        # Create session with both username and token
        session_value = _create_session("barry", "session-token", settings)

        # Mock get_user_token - should NOT be called
        with patch(
            "paperless_webdav.auth.paperless.get_user_token", new_callable=AsyncMock
        ) as mock_get_token:
            user = await get_current_user(session=session_value, settings=settings)

        assert user.username == "barry"
        assert user.token == "session-token"
        # DB lookup should NOT have been called since session has a token
        mock_get_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_session_returns_user_with_empty_token_for_oidc(
        self, mock_oidc_settings
    ):
        """_validate_session should return user even with empty token (for DB lookup later)."""
        settings = get_settings()

        # Create session with empty token
        session_value = _create_session("barry", "", settings)

        # _validate_session should return the user (with empty token)
        # The token loading from DB happens in get_current_user, not _validate_session
        user = _validate_session(session_value, settings)

        assert user is not None
        assert user.username == "barry"
        assert user.token == ""
