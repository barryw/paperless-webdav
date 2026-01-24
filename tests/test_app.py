"""Tests for FastAPI application."""

import pytest
from httpx import ASGITransport, AsyncClient

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
