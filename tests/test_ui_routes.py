"""Tests for UI routes."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from itsdangerous import URLSafeTimedSerializer

from paperless_webdav.app import create_app
from paperless_webdav.dependencies import get_db_session
from paperless_webdav.models import Share


@pytest.fixture
def app(mock_settings):
    """Create test application."""
    return create_app()


@pytest.fixture
def auth_cookie(mock_settings):
    """Create a valid session cookie for testing authenticated routes."""
    serializer = URLSafeTimedSerializer("test-secret-key-for-sessions")
    session_value = serializer.dumps({"username": "testuser", "token": "test-token"})
    return {"session": session_value}


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def app_with_db(mock_settings, mock_db_session):
    """Create test application with mocked database session."""
    app = create_app()

    async def override_get_db_session():
        yield mock_db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    return app


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
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

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
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

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
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

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
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/ui/login",
                data={"username": "testuser", "password": "testpass"},
                follow_redirects=False,
            )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "error" in response.text.lower()


# --- Share List Page Tests ---


@pytest.mark.asyncio
async def test_shares_list_requires_auth(app_with_db):
    """Shares page should redirect to login when not authenticated."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get("/ui/shares", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"


@pytest.mark.asyncio
async def test_shares_list_renders_when_authenticated(app_with_db, auth_cookie):
    """Shares page should render when authenticated."""
    with patch(
        "paperless_webdav.ui.routes.get_user_shares", new_callable=AsyncMock
    ) as mock_get_shares:
        mock_get_shares.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get("/ui/shares", cookies=auth_cookie)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_shares_list_shows_empty_state(app_with_db, auth_cookie):
    """Shares page should show empty state when user has no shares."""
    with patch(
        "paperless_webdav.ui.routes.get_user_shares", new_callable=AsyncMock
    ) as mock_get_shares:
        mock_get_shares.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get("/ui/shares", cookies=auth_cookie)

    assert response.status_code == 200
    assert "No shares yet" in response.text or "no shares" in response.text.lower()


@pytest.mark.asyncio
async def test_shares_list_shows_create_button(app_with_db, auth_cookie):
    """Shares page should have a create share button."""
    with patch(
        "paperless_webdav.ui.routes.get_user_shares", new_callable=AsyncMock
    ) as mock_get_shares:
        mock_get_shares.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get("/ui/shares", cookies=auth_cookie)

    assert response.status_code == 200
    assert "/ui/shares/new" in response.text


@pytest.mark.asyncio
async def test_shares_list_displays_shares(app_with_db, auth_cookie):
    """Shares page should display user's shares in a table."""
    mock_share = MagicMock(spec=Share)
    mock_share.id = uuid4()
    mock_share.name = "test-share"
    mock_share.include_tags = ["inbox", "documents"]
    mock_share.expires_at = None

    with patch(
        "paperless_webdav.ui.routes.get_user_shares", new_callable=AsyncMock
    ) as mock_get_shares:
        mock_get_shares.return_value = [mock_share]

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get("/ui/shares", cookies=auth_cookie)

    assert response.status_code == 200
    assert "test-share" in response.text
    assert "inbox" in response.text
    assert "documents" in response.text


@pytest.mark.asyncio
async def test_shares_list_shows_edit_link(app_with_db, auth_cookie):
    """Shares page should have an edit link for each share."""
    mock_share = MagicMock(spec=Share)
    mock_share.id = uuid4()
    mock_share.name = "test-share"
    mock_share.include_tags = ["inbox"]
    mock_share.expires_at = None

    with patch(
        "paperless_webdav.ui.routes.get_user_shares", new_callable=AsyncMock
    ) as mock_get_shares:
        mock_get_shares.return_value = [mock_share]

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get("/ui/shares", cookies=auth_cookie)

    assert response.status_code == 200
    assert f"/ui/shares/{mock_share.name}/edit" in response.text


@pytest.mark.asyncio
async def test_shares_list_shows_delete_button(app_with_db, auth_cookie):
    """Shares page should have an HTMX delete button for each share."""
    mock_share = MagicMock(spec=Share)
    mock_share.id = uuid4()
    mock_share.name = "test-share"
    mock_share.include_tags = ["inbox"]
    mock_share.expires_at = None

    with patch(
        "paperless_webdav.ui.routes.get_user_shares", new_callable=AsyncMock
    ) as mock_get_shares:
        mock_get_shares.return_value = [mock_share]

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get("/ui/shares", cookies=auth_cookie)

    assert response.status_code == 200
    assert "hx-delete" in response.text
    assert f"/ui/shares/{mock_share.name}" in response.text


@pytest.mark.asyncio
async def test_shares_list_displays_expiry_date(app_with_db, auth_cookie):
    """Shares page should display expiry date if set."""
    mock_share = MagicMock(spec=Share)
    mock_share.id = uuid4()
    mock_share.name = "expiring-share"
    mock_share.include_tags = ["temp"]
    mock_share.expires_at = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    with patch(
        "paperless_webdav.ui.routes.get_user_shares", new_callable=AsyncMock
    ) as mock_get_shares:
        mock_get_shares.return_value = [mock_share]

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get("/ui/shares", cookies=auth_cookie)

    assert response.status_code == 200
    assert "2025" in response.text


# --- Create/Edit Share Form Tests ---


@pytest.mark.asyncio
async def test_create_share_page_renders(app_with_db, auth_cookie, mock_settings):
    """Create share page should render form."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get("/ui/shares/new", cookies=auth_cookie)

    assert response.status_code == 200
    assert "Create Share" in response.text
    assert 'name="name"' in response.text


@pytest.mark.asyncio
async def test_create_share_page_requires_auth(app_with_db):
    """Create share page should redirect to login when not authenticated."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get("/ui/shares/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"


@pytest.mark.asyncio
async def test_create_share_page_has_all_fields(app_with_db, auth_cookie, mock_settings):
    """Create share page should have all required form fields."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get("/ui/shares/new", cookies=auth_cookie)

    assert response.status_code == 200
    assert 'name="include_tags"' in response.text
    assert 'name="exclude_tags"' in response.text
    assert 'name="read_only"' in response.text
    assert 'name="done_folder_enabled"' in response.text
    assert 'name="done_folder_name"' in response.text
    assert 'name="done_tag"' in response.text
    assert 'name="expires_at"' in response.text
    assert 'name="allowed_users"' in response.text


@pytest.mark.asyncio
async def test_edit_share_page_requires_auth(app_with_db):
    """Edit share page should redirect to login when not authenticated."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get("/ui/shares/test-share/edit", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"


@pytest.mark.asyncio
async def test_edit_share_page_renders_with_data(app_with_db, auth_cookie, mock_settings):
    """Edit share page should render form with existing share data."""
    mock_share = MagicMock(spec=Share)
    mock_share.id = uuid4()
    mock_share.name = "test-share"
    mock_share.include_tags = ["inbox", "documents"]
    mock_share.exclude_tags = ["private"]
    mock_share.read_only = True
    mock_share.done_folder_enabled = True
    mock_share.done_folder_name = "processed"
    mock_share.done_tag = "done"
    mock_share.expires_at = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    mock_share.allowed_users = ["user1", "user2"]

    with patch(
        "paperless_webdav.ui.routes.get_share_by_name", new_callable=AsyncMock
    ) as mock_get_share:
        mock_get_share.return_value = mock_share

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get("/ui/shares/test-share/edit", cookies=auth_cookie)

    assert response.status_code == 200
    assert "Edit Share" in response.text
    assert "test-share" in response.text
    assert "inbox" in response.text
    assert "documents" in response.text
    assert "private" in response.text
    assert "processed" in response.text
    assert "user1" in response.text


@pytest.mark.asyncio
async def test_edit_share_page_name_field_disabled(app_with_db, auth_cookie, mock_settings):
    """Edit share page should have name field disabled."""
    mock_share = MagicMock(spec=Share)
    mock_share.id = uuid4()
    mock_share.name = "test-share"
    mock_share.include_tags = []
    mock_share.exclude_tags = []
    mock_share.read_only = True
    mock_share.done_folder_enabled = False
    mock_share.done_folder_name = "done"
    mock_share.done_tag = None
    mock_share.expires_at = None
    mock_share.allowed_users = []

    with patch(
        "paperless_webdav.ui.routes.get_share_by_name", new_callable=AsyncMock
    ) as mock_get_share:
        mock_get_share.return_value = mock_share

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get("/ui/shares/test-share/edit", cookies=auth_cookie)

    assert response.status_code == 200
    # Check that name field is disabled
    assert "disabled" in response.text


@pytest.mark.asyncio
async def test_edit_share_page_redirects_if_not_found(app_with_db, auth_cookie, mock_settings):
    """Edit share page should redirect to shares list if share not found."""
    with patch(
        "paperless_webdav.ui.routes.get_share_by_name", new_callable=AsyncMock
    ) as mock_get_share:
        mock_get_share.return_value = None

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/shares/nonexistent/edit", cookies=auth_cookie, follow_redirects=False
            )

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/shares"


@pytest.mark.asyncio
async def test_create_share_page_has_javascript_toggle(app_with_db, auth_cookie, mock_settings):
    """Create share page should include JavaScript for done folder toggle."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get("/ui/shares/new", cookies=auth_cookie)

    assert response.status_code == 200
    assert "toggleDoneFolderFields" in response.text
