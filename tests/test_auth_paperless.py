# tests/test_auth_paperless.py
"""Tests for Paperless-native authentication."""

import pytest
import respx
from httpx import AsyncClient, ASGITransport, Response

from paperless_webdav.app import create_app


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

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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
        respx.post("http://paperless.test/api/token/").mock(
            return_value=Response(500)
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "barry", "password": "secret"},
            )

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_login_missing_username(self, app):
        """Missing username should return 422."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/auth/login",
                json={"password": "secret"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_missing_password(self, app):
        """Missing password should return 422."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_invalid_session(self, app):
        """Invalid session should return 401."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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
                json={"count": 1, "next": None, "previous": None, "results": [
                    {"id": 1, "name": "tax", "slug": "tax", "color": "#ff0000"}
                ]},
            )
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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
