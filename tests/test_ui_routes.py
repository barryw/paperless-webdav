"""Tests for UI routes."""

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
