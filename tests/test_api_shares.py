# tests/test_api_shares.py
"""Tests for share API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4
from dataclasses import dataclass
from datetime import datetime

from paperless_webdav.app import create_app
from paperless_webdav.api import shares as shares_module
from paperless_webdav.auth import AuthenticatedUser
from paperless_webdav.auth import paperless as auth_module


@dataclass
class MockShare:
    """Mock share for testing."""

    id: UUID
    name: str
    include_tags: list[str]
    exclude_tags: list[str]
    expires_at: datetime | None
    read_only: bool
    done_folder_enabled: bool
    done_folder_name: str
    done_tag: str | None
    allowed_users: list[str]
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self):
        now = datetime.now()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now


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
async def test_list_shares_empty(app_with_auth, mock_user):
    """List shares should return empty list initially."""
    with patch.object(shares_module, "get_user_shares", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.get("/api/shares")

        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
async def test_create_share(app_with_auth, mock_user):
    """Create share should return the new share."""
    with patch.object(
        shares_module, "get_share_by_name", new_callable=AsyncMock
    ) as mock_get_by_name:
        mock_get_by_name.return_value = None  # No existing share

        with patch.object(
            shares_module, "create_share", new_callable=AsyncMock
        ) as mock_create:
            share_id = uuid4()
            mock_create.return_value = MockShare(
                id=share_id,
                name="tax2025",
                include_tags=["tax", "2025"],
                exclude_tags=[],
                expires_at=None,
                read_only=True,
                done_folder_enabled=False,
                done_folder_name="done",
                done_tag=None,
                allowed_users=[],
            )

            async with AsyncClient(
                transport=ASGITransport(app=app_with_auth), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/shares",
                    json={
                        "name": "tax2025",
                        "include_tags": ["tax", "2025"],
                    },
                )

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "tax2025"
            assert data["include_tags"] == ["tax", "2025"]


@pytest.mark.asyncio
async def test_create_share_invalid_name(app_with_auth, mock_user):
    """Create share with invalid name should return 422."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_auth), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/shares",
            json={
                "name": "invalid name!",  # spaces and special chars not allowed
                "include_tags": ["tax"],
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_share(app_with_auth, mock_user):
    """Delete share should return 204."""
    with patch.object(shares_module, "delete_share", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = True

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.delete("/api/shares/tax2025")

        assert response.status_code == 204


@pytest.mark.asyncio
async def test_list_shares_with_items(app_with_auth, mock_user):
    """List shares should return shares for the user."""
    share_id = uuid4()
    with patch.object(shares_module, "get_user_shares", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [
            MockShare(
                id=share_id,
                name="documents",
                include_tags=["important"],
                exclude_tags=["archived"],
                expires_at=None,
                read_only=False,
                done_folder_enabled=True,
                done_folder_name="processed",
                done_tag="processed",
                allowed_users=["alice"],
            )
        ]

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.get("/api/shares")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "documents"
        assert data[0]["include_tags"] == ["important"]
        assert data[0]["done_folder_enabled"] is True


@pytest.mark.asyncio
async def test_get_share(app_with_auth, mock_user):
    """Get specific share by name."""
    share_id = uuid4()
    with patch.object(
        shares_module, "get_share_by_name", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = MockShare(
            id=share_id,
            name="tax2025",
            include_tags=["tax", "2025"],
            exclude_tags=[],
            expires_at=None,
            read_only=True,
            done_folder_enabled=False,
            done_folder_name="done",
            done_tag=None,
            allowed_users=[],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.get("/api/shares/tax2025")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "tax2025"


@pytest.mark.asyncio
async def test_get_share_not_found(app_with_auth, mock_user):
    """Get non-existent share should return 404."""
    with patch.object(
        shares_module, "get_share_by_name", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = None

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.get("/api/shares/nonexistent")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_share(app_with_auth, mock_user):
    """Update share should return updated share."""
    share_id = uuid4()
    with patch.object(
        shares_module, "get_share_by_name", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = MockShare(
            id=share_id,
            name="tax2025",
            include_tags=["tax", "2025"],
            exclude_tags=[],
            expires_at=None,
            read_only=True,
            done_folder_enabled=False,
            done_folder_name="done",
            done_tag=None,
            allowed_users=[],
        )

        with patch.object(
            shares_module, "update_share", new_callable=AsyncMock
        ) as mock_update:
            mock_update.return_value = MockShare(
                id=share_id,
                name="tax2025",
                include_tags=["tax", "2025", "receipts"],  # Updated
                exclude_tags=["personal"],  # Updated
                expires_at=None,
                read_only=True,
                done_folder_enabled=False,
                done_folder_name="done",
                done_tag=None,
                allowed_users=[],
            )

            async with AsyncClient(
                transport=ASGITransport(app=app_with_auth), base_url="http://test"
            ) as client:
                response = await client.put(
                    "/api/shares/tax2025",
                    json={
                        "include_tags": ["tax", "2025", "receipts"],
                        "exclude_tags": ["personal"],
                    },
                )

            assert response.status_code == 200
            data = response.json()
            assert data["include_tags"] == ["tax", "2025", "receipts"]
            assert data["exclude_tags"] == ["personal"]


@pytest.mark.asyncio
async def test_delete_share_not_found(app_with_auth, mock_user):
    """Delete non-existent share should return 404."""
    with patch.object(shares_module, "delete_share", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = False

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.delete("/api/shares/nonexistent")

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_share_duplicate_name(app_with_auth, mock_user):
    """Create share with existing name should return 409."""
    with patch.object(
        shares_module, "get_share_by_name", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = MockShare(
            id=uuid4(),
            name="existing",
            include_tags=["tax"],
            exclude_tags=[],
            expires_at=None,
            read_only=True,
            done_folder_enabled=False,
            done_folder_name="done",
            done_tag=None,
            allowed_users=[],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_auth), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/shares",
                json={
                    "name": "existing",
                    "include_tags": ["tax"],
                },
            )

        assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_share_done_folder_requires_tag(app_with_auth, mock_user):
    """Create share with done_folder_enabled but no done_tag should return 422."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_auth), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/shares",
            json={
                "name": "test-share",
                "include_tags": ["test"],
                "done_folder_enabled": True,
                # done_tag is missing
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_share_with_done_folder(app_with_auth, mock_user):
    """Create share with done folder configured."""
    with patch.object(
        shares_module, "get_share_by_name", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = None

        with patch.object(
            shares_module, "create_share", new_callable=AsyncMock
        ) as mock_create:
            share_id = uuid4()
            mock_create.return_value = MockShare(
                id=share_id,
                name="inbox",
                include_tags=["inbox"],
                exclude_tags=[],
                expires_at=None,
                read_only=False,
                done_folder_enabled=True,
                done_folder_name="processed",
                done_tag="processed",
                allowed_users=[],
            )

            async with AsyncClient(
                transport=ASGITransport(app=app_with_auth), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/shares",
                    json={
                        "name": "inbox",
                        "include_tags": ["inbox"],
                        "done_folder_enabled": True,
                        "done_folder_name": "processed",
                        "done_tag": "processed",
                    },
                )

            assert response.status_code == 201
            data = response.json()
            assert data["done_folder_enabled"] is True
            assert data["done_folder_name"] == "processed"
            assert data["done_tag"] == "processed"


@pytest.mark.asyncio
async def test_unauthenticated_request(mock_settings):
    """Requests without authentication should return 401."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/shares")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_share_name_validation_start_with_dash(app_with_auth, mock_user):
    """Share name starting with dash should return 422."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_auth), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/shares",
            json={
                "name": "-invalid",
                "include_tags": ["tax"],
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_share_name_validation_valid_names(app_with_auth, mock_user):
    """Valid share names should be accepted."""
    valid_names = ["a", "A", "1", "abc", "abc-123", "ABC-xyz-123"]

    for name in valid_names:
        with patch.object(
            shares_module, "get_share_by_name", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            with patch.object(
                shares_module, "create_share", new_callable=AsyncMock
            ) as mock_create:
                mock_create.return_value = MockShare(
                    id=uuid4(),
                    name=name,
                    include_tags=["test"],
                    exclude_tags=[],
                    expires_at=None,
                    read_only=True,
                    done_folder_enabled=False,
                    done_folder_name="done",
                    done_tag=None,
                    allowed_users=[],
                )

                async with AsyncClient(
                    transport=ASGITransport(app=app_with_auth), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/shares",
                        json={
                            "name": name,
                            "include_tags": ["test"],
                        },
                    )

                assert response.status_code == 201, f"Name '{name}' should be valid"
