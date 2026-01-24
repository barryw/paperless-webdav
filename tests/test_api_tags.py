# tests/test_api_tags.py
"""Tests for tags API endpoints."""

import pytest
import respx
from httpx import AsyncClient, ASGITransport, Response

from paperless_webdav.app import create_app
from paperless_webdav.auth import AuthenticatedUser
from paperless_webdav.auth import paperless as auth_module


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    return AuthenticatedUser(username="barry", token="test-token")


@pytest.fixture
def app_with_auth(mock_settings, mock_user):
    """Create test application with mocked auth."""
    app = create_app()

    # Override the auth dependency
    app.dependency_overrides[auth_module.get_current_user] = lambda: mock_user

    yield app

    # Cleanup
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_tags(app_with_auth):
    """List tags should proxy to Paperless API."""
    with respx.mock:
        respx.get("http://paperless.test/api/tags/").mock(
            return_value=Response(
                200,
                json={
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "results": [
                        {"id": 1, "name": "tax", "slug": "tax", "color": "#ff0000"},
                        {"id": 2, "name": "2025", "slug": "2025", "color": None},
                    ],
                },
            )
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.get("/api/tags")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "tax"
        assert data[0]["color"] == "#ff0000"
        assert data[1]["name"] == "2025"
        assert data[1]["color"] is None


@pytest.mark.asyncio
async def test_list_tags_empty(app_with_auth):
    """List tags should return empty list when no tags exist."""
    with respx.mock:
        respx.get("http://paperless.test/api/tags/").mock(
            return_value=Response(
                200,
                json={
                    "count": 0,
                    "next": None,
                    "previous": None,
                    "results": [],
                },
            )
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.get("/api/tags")

        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
async def test_search_tags(app_with_auth):
    """Search tags should filter by name."""
    with respx.mock:
        respx.get(
            "http://paperless.test/api/tags/", params={"name__icontains": "tax"}
        ).mock(
            return_value=Response(
                200,
                json={
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {"id": 1, "name": "tax", "slug": "tax", "color": "#ff0000"},
                    ],
                },
            )
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.get("/api/tags/search", params={"q": "tax"})

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "tax"


@pytest.mark.asyncio
async def test_search_tags_no_results(app_with_auth):
    """Search tags should return empty list when no matches."""
    with respx.mock:
        respx.get(
            "http://paperless.test/api/tags/", params={"name__icontains": "nonexistent"}
        ).mock(
            return_value=Response(
                200,
                json={
                    "count": 0,
                    "next": None,
                    "previous": None,
                    "results": [],
                },
            )
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.get("/api/tags/search", params={"q": "nonexistent"})

        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
async def test_search_tags_missing_query(app_with_auth):
    """Search tags without query parameter should return 422."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_auth), base_url="http://test"
    ) as client:
        response = await client.get("/api/tags/search")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_tags_unauthenticated(mock_settings):
    """List tags without authentication should return 401."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/tags")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_tags_unauthenticated(mock_settings):
    """Search tags without authentication should return 401."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/tags/search", params={"q": "tax"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_tags_with_pagination(app_with_auth):
    """List tags should handle paginated responses from Paperless."""
    call_count = 0

    def handle_tags_request(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return Response(
                200,
                json={
                    "count": 3,
                    "next": "http://paperless.test/api/tags/?page=2",
                    "previous": None,
                    "results": [
                        {"id": 1, "name": "tax", "slug": "tax", "color": "#ff0000"},
                    ],
                },
            )
        else:
            return Response(
                200,
                json={
                    "count": 3,
                    "next": None,
                    "previous": "http://paperless.test/api/tags/",
                    "results": [
                        {"id": 2, "name": "2025", "slug": "2025", "color": None},
                        {"id": 3, "name": "receipts", "slug": "receipts", "color": "#00ff00"},
                    ],
                },
            )

    with respx.mock:
        respx.get(url__startswith="http://paperless.test/api/tags/").mock(
            side_effect=handle_tags_request
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.get("/api/tags")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["name"] == "tax"
        assert data[1]["name"] == "2025"
        assert data[2]["name"] == "receipts"
