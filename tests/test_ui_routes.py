"""Tests for UI routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from paperless_webdav.app import create_app


@pytest.fixture
def app(mock_settings):
    """Create test application."""
    return create_app()


@pytest.mark.asyncio
async def test_login_page_renders(app):
    """Login page should render without authentication."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ui/login")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Login" in response.text


@pytest.mark.asyncio
async def test_login_form_redirects_on_success(app, mock_settings):
    """Successful login should redirect to shares page."""
    with patch("paperless_webdav.auth.paperless.httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "test-token"}
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/ui/login",
                data={"username": "testuser", "password": "testpass"},
                follow_redirects=False,
            )

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/shares"


@pytest.mark.asyncio
async def test_login_form_sets_session_cookie_on_success(app, mock_settings):
    """Successful login should set session cookie."""
    with patch("paperless_webdav.auth.paperless.httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "test-token"}
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/ui/login",
                data={"username": "testuser", "password": "testpass"},
                follow_redirects=False,
            )

    assert "session" in response.cookies


@pytest.mark.asyncio
async def test_login_form_shows_error_on_invalid_credentials(app, mock_settings):
    """Invalid credentials should re-render login page with error."""
    with patch("paperless_webdav.auth.paperless.httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/ui/login",
                data={"username": "testuser", "password": "wrongpass"},
                follow_redirects=False,
            )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Invalid credentials" in response.text


@pytest.mark.asyncio
async def test_login_form_shows_error_on_server_error(app, mock_settings):
    """Server error should re-render login page with error."""
    with patch("paperless_webdav.auth.paperless.httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/ui/login",
                data={"username": "testuser", "password": "testpass"},
                follow_redirects=False,
            )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "error" in response.text.lower()
