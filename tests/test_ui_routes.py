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
from paperless_webdav.paperless_client import PaperlessTag, PaperlessUser


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
    # Tag fields use HTMX autocomplete containers with data-field attributes
    assert 'data-field="include_tags"' in response.text
    assert 'data-field="exclude_tags"' in response.text
    assert 'data-field="done_tag"' in response.text
    # Other fields are standard inputs
    assert 'name="read_only"' in response.text
    assert 'name="done_folder_enabled"' in response.text
    assert 'name="done_folder_name"' in response.text
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


# --- Tag Autocomplete Tests ---


@pytest.mark.asyncio
async def test_tag_suggestions_returns_matches(app_with_db, auth_cookie, mock_settings):
    """Tag suggestions should return matching tags from Paperless."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_tags = AsyncMock(
            return_value=[
                PaperlessTag(id=1, name="invoices", slug="invoices", color="#ff0000"),
                PaperlessTag(id=2, name="income", slug="income", color="#00ff00"),
            ]
        )
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/tag-suggestions",
                params={"q": "in", "field": "include_tags"},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    assert "invoices" in response.text
    assert "income" in response.text


@pytest.mark.asyncio
async def test_tag_suggestions_requires_auth(app_with_db):
    """Tag suggestions endpoint should require authentication."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get(
            "/ui/partials/tag-suggestions",
            params={"q": "test", "field": "include_tags"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tag_suggestions_shows_color_indicator(app_with_db, auth_cookie, mock_settings):
    """Tag suggestions should display color indicators."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_tags = AsyncMock(
            return_value=[
                PaperlessTag(id=1, name="invoices", slug="invoices", color="#ff0000"),
            ]
        )
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/tag-suggestions",
                params={"q": "inv", "field": "include_tags"},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    assert "#ff0000" in response.text


@pytest.mark.asyncio
async def test_tag_suggestions_empty_query_returns_empty(app_with_db, auth_cookie, mock_settings):
    """Tag suggestions with empty query should not search."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_tags = AsyncMock(return_value=[])
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/tag-suggestions",
                params={"q": "", "field": "include_tags"},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    # Should not have called search_tags with empty query
    mock_client.search_tags.assert_not_called()


@pytest.mark.asyncio
async def test_tag_suggestions_no_matches_shows_message(app_with_db, auth_cookie, mock_settings):
    """Tag suggestions with no matches should show appropriate message."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_tags = AsyncMock(return_value=[])
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/tag-suggestions",
                params={"q": "nonexistent", "field": "include_tags"},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    assert "No tags found" in response.text
    assert "nonexistent" in response.text


@pytest.mark.asyncio
async def test_tag_suggestions_single_select_field(app_with_db, auth_cookie, mock_settings):
    """Tag suggestions for done_tag should indicate single select mode."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_tags = AsyncMock(
            return_value=[
                PaperlessTag(id=1, name="processed", slug="processed", color="#00ff00"),
            ]
        )
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/tag-suggestions",
                params={"q": "proc", "field": "done_tag"},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    assert 'data-single="true"' in response.text


@pytest.mark.asyncio
async def test_tag_suggestions_multi_select_field(app_with_db, auth_cookie, mock_settings):
    """Tag suggestions for include_tags should indicate multi select mode."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_tags = AsyncMock(
            return_value=[
                PaperlessTag(id=1, name="invoices", slug="invoices", color="#ff0000"),
            ]
        )
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/tag-suggestions",
                params={"q": "inv", "field": "include_tags"},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    assert 'data-single="false"' in response.text


@pytest.mark.asyncio
async def test_form_has_htmx_autocomplete(app_with_db, auth_cookie, mock_settings):
    """Create share form should have HTMX autocomplete for tag fields."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get("/ui/shares/new", cookies=auth_cookie)

    assert response.status_code == 200
    assert "hx-get" in response.text
    assert "/ui/partials/tag-suggestions" in response.text
    assert "hx-trigger" in response.text
    assert "hx-target" in response.text


# --- User Autocomplete Tests ---


@pytest.mark.asyncio
async def test_user_suggestions_returns_matches(app_with_db, auth_cookie, mock_settings):
    """User suggestions should return matching users from Paperless."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_users = AsyncMock(
            return_value=[
                PaperlessUser(id=1, username="alice", first_name="Alice", last_name="Smith"),
                PaperlessUser(id=2, username="alicia", first_name="Alicia", last_name="Jones"),
            ]
        )
        mock_client.get_users = AsyncMock(return_value=[])  # Not called when search returns results
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/user-suggestions",
                params={"q": "ali"},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    assert "alice" in response.text
    assert "alicia" in response.text
    assert "Alice" in response.text
    assert "Smith" in response.text


@pytest.mark.asyncio
async def test_user_suggestions_requires_auth(app_with_db):
    """User suggestions endpoint should require authentication."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get(
            "/ui/partials/user-suggestions",
            params={"q": "test"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_suggestions_shows_fallback_on_permission_denied(
    app_with_db, auth_cookie, mock_settings
):
    """User suggestions should show fallback message when user lacks permission."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_users = AsyncMock(return_value=[])  # Empty due to 403
        mock_client.get_users = AsyncMock(return_value=[])  # Also empty (permission denied)
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/user-suggestions",
                params={"q": "test"},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    assert "Enter usernames manually" in response.text


@pytest.mark.asyncio
async def test_user_suggestions_empty_query_returns_empty(app_with_db, auth_cookie, mock_settings):
    """User suggestions with empty query should not search."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_users = AsyncMock(return_value=[])
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/user-suggestions",
                params={"q": ""},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    # Should not have called search_users with empty query
    mock_client.search_users.assert_not_called()


@pytest.mark.asyncio
async def test_user_suggestions_no_matches_shows_message(app_with_db, auth_cookie, mock_settings):
    """User suggestions with no matches should show appropriate message."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_users = AsyncMock(return_value=[])
        # Return at least one user to show we have permission but no matches
        mock_client.get_users = AsyncMock(
            return_value=[PaperlessUser(id=1, username="bob", first_name="Bob", last_name="")]
        )
        mock_client_class.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db), base_url="http://test"
        ) as client:
            response = await client.get(
                "/ui/partials/user-suggestions",
                params={"q": "nonexistent"},
                cookies=auth_cookie,
            )

    assert response.status_code == 200
    assert "No users found" in response.text
    assert "nonexistent" in response.text


@pytest.mark.asyncio
async def test_form_has_user_autocomplete(app_with_db, auth_cookie, mock_settings):
    """Create share form should have HTMX autocomplete for allowed_users field."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        response = await client.get("/ui/shares/new", cookies=auth_cookie)

    assert response.status_code == 200
    assert "/ui/partials/user-suggestions" in response.text
    assert 'data-field="allowed_users"' in response.text
    assert "allowed_users_chips" in response.text
