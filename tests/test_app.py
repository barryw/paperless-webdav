"""Tests for FastAPI application."""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

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


@pytest.mark.asyncio
async def test_ready_endpoint_with_db_connected(mock_settings):
    """Ready endpoint should return database connected when session is available."""
    from paperless_webdav.dependencies import get_db_session_optional

    # Create a mock session
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())

    app = create_app()

    # Override the session dependency
    async def mock_get_session():
        yield mock_session

    app.dependency_overrides[get_db_session_optional] = mock_get_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ready")

        # Database check should pass
        data = response.json()
        assert data["checks"]["database"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_app_has_required_routers(app):
    """App should include all required routers."""
    routes = [route.path for route in app.routes]

    # Health routes
    assert "/health" in routes
    assert "/ready" in routes

    # Share routes
    assert "/api/shares" in routes
    assert "/api/shares/{name}" in routes

    # Tag routes
    assert "/api/tags" in routes

    # Auth routes
    assert "/api/auth/login" in routes
