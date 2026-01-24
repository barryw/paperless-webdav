# Admin UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Build a web UI for users to manage their Paperless-ngx WebDAV shares with HTMX-powered tag autocomplete.

**Architecture:** Jinja2 templates served by FastAPI, HTMX for dynamic interactions without page reloads, Tailwind CSS via CDN for styling. UI routes under `/ui/*` prefix, partials under `/ui/partials/*` for HTMX fragments.

**Tech Stack:** FastAPI, Jinja2, HTMX, Tailwind CSS (CDN), existing auth system

---

## Task 1: Jinja2 Template Setup

**Files:**
- Create: `src/paperless_webdav/ui/__init__.py`
- Create: `src/paperless_webdav/ui/routes.py`
- Create: `src/paperless_webdav/ui/templates/base.html`
- Modify: `src/paperless_webdav/app.py`
- Create: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

```python
# tests/test_ui_routes.py
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
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_login_page_renders -v`
Expected: FAIL with 404 (route not found)

**Step 3: Create UI module structure**

```python
# src/paperless_webdav/ui/__init__.py
"""UI module for admin web interface."""

from paperless_webdav.ui.routes import router as ui_router

__all__ = ["ui_router"]
```

```python
# src/paperless_webdav/ui/routes.py
"""UI routes for admin web interface."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/ui", tags=["ui"])

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Render the login page."""
    return templates.TemplateResponse(
        request=request,
        name="login.html",
    )
```

**Step 4: Create base template with Tailwind and HTMX**

```html
<!-- src/paperless_webdav/ui/templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Paperless WebDAV{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
</head>
<body class="bg-gray-100 min-h-screen">
    {% block content %}{% endblock %}
</body>
</html>
```

**Step 5: Create login template**

```html
<!-- src/paperless_webdav/ui/templates/login.html -->
{% extends "base.html" %}

{% block title %}Login - Paperless WebDAV{% endblock %}

{% block content %}
<div class="flex items-center justify-center min-h-screen">
    <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 class="text-2xl font-bold text-center mb-6">Login</h1>
        <form hx-post="/api/auth/login" hx-target="#error-message" hx-swap="innerHTML">
            <div class="mb-4">
                <label for="username" class="block text-sm font-medium text-gray-700 mb-1">Username</label>
                <input type="text" id="username" name="username" required
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <div class="mb-6">
                <label for="password" class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input type="password" id="password" name="password" required
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <div id="error-message" class="mb-4 text-red-600 text-sm"></div>
            <button type="submit"
                class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500">
                Sign In
            </button>
        </form>
    </div>
</div>
{% endblock %}
```

**Step 6: Register UI router in app.py**

Add to `src/paperless_webdav/app.py` imports:
```python
from paperless_webdav.ui import ui_router
```

Add to `create_app()` after other routers:
```python
    app.include_router(ui_router)
```

**Step 7: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_login_page_renders -v`
Expected: PASS

**Step 8: Commit**

```bash
git add src/paperless_webdav/ui/ src/paperless_webdav/app.py tests/test_ui_routes.py
git commit -m "feat: add Jinja2 template setup with login page

- Create UI module with routes and templates
- Add base.html with Tailwind CSS and HTMX
- Add login page template
- Wire UI router to FastAPI app

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Login Form Submission

**Files:**
- Modify: `src/paperless_webdav/ui/templates/login.html`
- Modify: `src/paperless_webdav/ui/routes.py`
- Modify: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_ui_routes.py
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_login_form_redirects_on_success(app, mock_settings):
    """Successful login should redirect to shares page."""
    with patch("paperless_webdav.auth.paperless.httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
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
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_login_form_redirects_on_success -v`
Expected: FAIL (POST to /ui/login not implemented)

**Step 3: Add login POST handler**

Add to `src/paperless_webdav/ui/routes.py`:

```python
from typing import Annotated

import httpx
from fastapi import Depends, Form, Response
from fastapi.responses import RedirectResponse

from paperless_webdav.auth.paperless import _create_session
from paperless_webdav.config import get_settings, Settings
from paperless_webdav.logging import get_logger

logger = get_logger(__name__)


@router.post("/login")
async def login_submit(
    request: Request,
    response: Response,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Handle login form submission."""
    paperless_url = settings.paperless_url.rstrip("/")
    token_url = f"{paperless_url}/api/token/"

    try:
        async with httpx.AsyncClient() as client:
            paperless_response = await client.post(
                token_url,
                json={"username": username, "password": password},
            )
    except httpx.RequestError:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Failed to connect to Paperless server"},
        )

    if paperless_response.status_code != 200:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid username or password"},
        )

    token = paperless_response.json().get("token")
    session_value = _create_session(username, token, settings)

    redirect = RedirectResponse(url="/ui/shares", status_code=303)
    redirect.set_cookie(
        key="session",
        value=session_value,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_expiry_hours * 3600,
    )
    return redirect
```

**Step 4: Update login template to handle errors**

Update `src/paperless_webdav/ui/templates/login.html` form section:

```html
{% block content %}
<div class="flex items-center justify-center min-h-screen">
    <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 class="text-2xl font-bold text-center mb-6">Login</h1>
        {% if error %}
        <div class="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
            {{ error }}
        </div>
        {% endif %}
        <form method="post" action="/ui/login">
            <div class="mb-4">
                <label for="username" class="block text-sm font-medium text-gray-700 mb-1">Username</label>
                <input type="text" id="username" name="username" required
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <div class="mb-6">
                <label for="password" class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input type="password" id="password" name="password" required
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <button type="submit"
                class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500">
                Sign In
            </button>
        </form>
    </div>
</div>
{% endblock %}
```

**Step 5: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_login_form_redirects_on_success -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/paperless_webdav/ui/ tests/test_ui_routes.py
git commit -m "feat: add login form submission with redirect

- Handle POST /ui/login with form data
- Validate against Paperless API
- Set session cookie on success
- Show error message on failure

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Share List Page

**Files:**
- Modify: `src/paperless_webdav/ui/routes.py`
- Create: `src/paperless_webdav/ui/templates/shares/list.html`
- Modify: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_ui_routes.py
from paperless_webdav.auth import AuthenticatedUser


@pytest.fixture
def auth_cookie(mock_settings):
    """Create a valid auth session cookie."""
    from paperless_webdav.auth.paperless import _create_session
    from paperless_webdav.config import get_settings
    settings = get_settings()
    return _create_session("testuser", "test-token", settings)


@pytest.mark.asyncio
async def test_shares_list_requires_auth(app):
    """Shares page should redirect to login when not authenticated."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ui/shares", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"


@pytest.mark.asyncio
async def test_shares_list_renders_when_authenticated(app, auth_cookie, mock_settings):
    """Shares page should render when authenticated."""
    from paperless_webdav.ui import routes as ui_routes

    with patch.object(ui_routes, "get_user_shares", new_callable=AsyncMock) as mock_shares:
        mock_shares.return_value = []

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/ui/shares",
                cookies={"session": auth_cookie},
            )

    assert response.status_code == 200
    assert "Your Shares" in response.text
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_shares_list_requires_auth -v`
Expected: FAIL (route not found)

**Step 3: Create shares directory and list template**

```html
<!-- src/paperless_webdav/ui/templates/shares/list.html -->
{% extends "base.html" %}

{% block title %}Your Shares - Paperless WebDAV{% endblock %}

{% block content %}
<div class="max-w-6xl mx-auto px-4 py-8">
    <!-- Header -->
    <div class="flex justify-between items-center mb-6">
        <h1 class="text-2xl font-bold text-gray-900">Your Shares</h1>
        <div class="flex items-center gap-4">
            <span class="text-gray-600">{{ username }}</span>
            <form action="/ui/logout" method="post" class="inline">
                <button type="submit" class="text-blue-600 hover:text-blue-800">Logout</button>
            </form>
        </div>
    </div>

    <!-- Flash messages -->
    {% if flash_message %}
    <div class="mb-4 p-3 rounded {% if flash_type == 'error' %}bg-red-100 border border-red-400 text-red-700{% else %}bg-green-100 border border-green-400 text-green-700{% endif %}">
        {{ flash_message }}
    </div>
    {% endif %}

    <!-- Create button -->
    <div class="mb-6">
        <a href="/ui/shares/new"
            class="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
            </svg>
            Create Share
        </a>
    </div>

    <!-- Shares table -->
    {% if shares %}
    <div class="bg-white shadow rounded-lg overflow-hidden">
        <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
                <tr>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Include Tags</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Expires</th>
                    <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200" id="shares-list">
                {% for share in shares %}
                <tr id="share-{{ share.id }}">
                    <td class="px-6 py-4 whitespace-nowrap">
                        <span class="font-medium text-gray-900">{{ share.name }}</span>
                    </td>
                    <td class="px-6 py-4">
                        <div class="flex flex-wrap gap-1">
                            {% for tag in share.include_tags %}
                            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                                {{ tag }}
                            </span>
                            {% endfor %}
                        </div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {{ share.expires_at.strftime('%Y-%m-%d') if share.expires_at else 'Never' }}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <a href="/ui/shares/{{ share.name }}/edit" class="text-blue-600 hover:text-blue-900 mr-4">Edit</a>
                        <button
                            hx-delete="/ui/shares/{{ share.name }}"
                            hx-confirm="Are you sure you want to delete '{{ share.name }}'?"
                            hx-target="#share-{{ share.id }}"
                            hx-swap="outerHTML"
                            class="text-red-600 hover:text-red-900">
                            Delete
                        </button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <div class="bg-white shadow rounded-lg p-8 text-center">
        <p class="text-gray-500 mb-4">You don't have any shares yet.</p>
        <a href="/ui/shares/new" class="text-blue-600 hover:text-blue-800">Create your first share</a>
    </div>
    {% endif %}
</div>
{% endblock %}
```

**Step 4: Add shares list route**

Add to `src/paperless_webdav/ui/routes.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from paperless_webdav.auth import AuthenticatedUser, get_current_user_optional
from paperless_webdav.dependencies import get_db_session
from paperless_webdav.services import shares as share_service


async def get_user_shares(session: AsyncSession, username: str):
    """Get shares for user - wrapper for easy mocking."""
    return await share_service.get_user_shares(session, username)


@router.get("/shares", response_class=HTMLResponse)
async def shares_list(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)] = None,
) -> Response:
    """Render the shares list page."""
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    shares = await get_user_shares(session, current_user.username)

    return templates.TemplateResponse(
        request=request,
        name="shares/list.html",
        context={
            "shares": shares,
            "username": current_user.username,
        },
    )
```

**Step 5: Create shares template directory**

Run: `mkdir -p src/paperless_webdav/ui/templates/shares`

**Step 6: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/paperless_webdav/ui/ tests/test_ui_routes.py
git commit -m "feat: add share list page with auth protection

- Require authentication for /ui/shares
- Redirect to login if not authenticated
- Display shares in table with tags as pills
- Add delete button with HTMX confirmation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create/Edit Share Form

**Files:**
- Modify: `src/paperless_webdav/ui/routes.py`
- Create: `src/paperless_webdav/ui/templates/shares/form.html`
- Modify: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_ui_routes.py

@pytest.mark.asyncio
async def test_create_share_page_renders(app, auth_cookie, mock_settings):
    """Create share page should render form."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/ui/shares/new",
            cookies={"session": auth_cookie},
        )

    assert response.status_code == 200
    assert "Create Share" in response.text
    assert 'name="name"' in response.text


@pytest.mark.asyncio
async def test_edit_share_page_renders(app, auth_cookie, mock_settings):
    """Edit share page should render form with existing data."""
    from paperless_webdav.ui import routes as ui_routes
    from uuid import uuid4

    mock_share = type("Share", (), {
        "id": uuid4(),
        "name": "test-share",
        "include_tags": ["tag1", "tag2"],
        "exclude_tags": [],
        "expires_at": None,
        "read_only": True,
        "done_folder_enabled": False,
        "done_folder_name": "done",
        "done_tag": None,
        "allowed_users": [],
    })()

    with patch.object(ui_routes, "get_share_by_name", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_share

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/ui/shares/test-share/edit",
                cookies={"session": auth_cookie},
            )

    assert response.status_code == 200
    assert "Edit Share" in response.text
    assert "test-share" in response.text
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_create_share_page_renders -v`
Expected: FAIL (route not found)

**Step 3: Create share form template**

```html
<!-- src/paperless_webdav/ui/templates/shares/form.html -->
{% extends "base.html" %}

{% block title %}{{ 'Edit' if share else 'Create' }} Share - Paperless WebDAV{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto px-4 py-8">
    <!-- Header -->
    <div class="flex justify-between items-center mb-6">
        <h1 class="text-2xl font-bold text-gray-900">{{ 'Edit' if share else 'Create' }} Share</h1>
        <a href="/ui/shares" class="text-gray-600 hover:text-gray-800">Back to list</a>
    </div>

    <!-- Error message -->
    {% if error %}
    <div class="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
        {{ error }}
    </div>
    {% endif %}

    <form method="post" class="bg-white shadow rounded-lg p-6 space-y-6">
        <!-- Name -->
        <div>
            <label for="name" class="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input type="text" id="name" name="name"
                value="{{ share.name if share else '' }}"
                {% if share %}disabled{% endif %}
                required
                pattern="[a-zA-Z0-9][a-zA-Z0-9-]*"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 {% if share %}bg-gray-100{% endif %}">
            <p class="mt-1 text-sm text-gray-500">Alphanumeric and dashes only, must start with letter or number</p>
            {% if share %}
            <input type="hidden" name="name" value="{{ share.name }}">
            {% endif %}
        </div>

        <!-- Include Tags -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Include Tags (required)</label>
            <div class="relative">
                <input type="text" id="include-tags-input"
                    placeholder="Type to search tags..."
                    hx-get="/ui/partials/tag-suggestions"
                    hx-trigger="keyup changed delay:300ms"
                    hx-target="#include-tags-suggestions"
                    hx-vals='{"field": "include_tags"}'
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                <div id="include-tags-suggestions" class="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg hidden"></div>
            </div>
            <div id="include-tags-chips" class="flex flex-wrap gap-2 mt-2">
                {% if share %}
                {% for tag in share.include_tags %}
                <span class="inline-flex items-center px-2 py-1 rounded-md text-sm bg-blue-100 text-blue-800">
                    {{ tag }}
                    <button type="button" onclick="removeTag('include_tags', '{{ tag }}')" class="ml-1 text-blue-600 hover:text-blue-800">&times;</button>
                    <input type="hidden" name="include_tags" value="{{ tag }}">
                </span>
                {% endfor %}
                {% endif %}
            </div>
        </div>

        <!-- Exclude Tags -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Exclude Tags (optional)</label>
            <div class="relative">
                <input type="text" id="exclude-tags-input"
                    placeholder="Type to search tags..."
                    hx-get="/ui/partials/tag-suggestions"
                    hx-trigger="keyup changed delay:300ms"
                    hx-target="#exclude-tags-suggestions"
                    hx-vals='{"field": "exclude_tags"}'
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                <div id="exclude-tags-suggestions" class="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg hidden"></div>
            </div>
            <div id="exclude-tags-chips" class="flex flex-wrap gap-2 mt-2">
                {% if share %}
                {% for tag in share.exclude_tags %}
                <span class="inline-flex items-center px-2 py-1 rounded-md text-sm bg-gray-100 text-gray-800">
                    {{ tag }}
                    <button type="button" onclick="removeTag('exclude_tags', '{{ tag }}')" class="ml-1 text-gray-600 hover:text-gray-800">&times;</button>
                    <input type="hidden" name="exclude_tags" value="{{ tag }}">
                </span>
                {% endfor %}
                {% endif %}
            </div>
        </div>

        <!-- Done Folder -->
        <div class="border rounded-md p-4">
            <div class="flex items-center mb-4">
                <input type="checkbox" id="done_folder_enabled" name="done_folder_enabled" value="true"
                    {% if share and share.done_folder_enabled %}checked{% endif %}
                    onchange="toggleDoneFolder(this.checked)"
                    class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded">
                <label for="done_folder_enabled" class="ml-2 block text-sm font-medium text-gray-700">
                    Enable Done Folder
                </label>
            </div>
            <div id="done-folder-options" class="space-y-4 {% if not share or not share.done_folder_enabled %}hidden{% endif %}">
                <div>
                    <label for="done_folder_name" class="block text-sm font-medium text-gray-700 mb-1">Folder Name</label>
                    <input type="text" id="done_folder_name" name="done_folder_name"
                        value="{{ share.done_folder_name if share else 'done' }}"
                        class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Done Tag (required when enabled)</label>
                    <div class="relative">
                        <input type="text" id="done-tag-input"
                            placeholder="Type to search tags..."
                            hx-get="/ui/partials/tag-suggestions"
                            hx-trigger="keyup changed delay:300ms"
                            hx-target="#done-tag-suggestions"
                            hx-vals='{"field": "done_tag", "single": "true"}'
                            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <div id="done-tag-suggestions" class="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg hidden"></div>
                    </div>
                    <div id="done-tag-chips" class="flex flex-wrap gap-2 mt-2">
                        {% if share and share.done_tag %}
                        <span class="inline-flex items-center px-2 py-1 rounded-md text-sm bg-green-100 text-green-800">
                            {{ share.done_tag }}
                            <button type="button" onclick="removeTag('done_tag', '{{ share.done_tag }}')" class="ml-1 text-green-600 hover:text-green-800">&times;</button>
                            <input type="hidden" name="done_tag" value="{{ share.done_tag }}">
                        </span>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>

        <!-- Read Only -->
        <div class="flex items-center">
            <input type="checkbox" id="read_only" name="read_only" value="true"
                {% if not share or share.read_only %}checked{% endif %}
                class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded">
            <label for="read_only" class="ml-2 block text-sm font-medium text-gray-700">
                Read Only
            </label>
        </div>

        <!-- Expires -->
        <div>
            <label for="expires_at" class="block text-sm font-medium text-gray-700 mb-1">Expires (optional)</label>
            <input type="datetime-local" id="expires_at" name="expires_at"
                value="{{ share.expires_at.strftime('%Y-%m-%dT%H:%M') if share and share.expires_at else '' }}"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
        </div>

        <!-- Allowed Users -->
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Allowed Users (optional)</label>
            <div class="relative">
                <input type="text" id="allowed-users-input"
                    placeholder="Type to search users..."
                    hx-get="/ui/partials/user-suggestions"
                    hx-trigger="keyup changed delay:300ms"
                    hx-target="#allowed-users-suggestions"
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                <div id="allowed-users-suggestions" class="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg hidden"></div>
            </div>
            <div id="allowed-users-chips" class="flex flex-wrap gap-2 mt-2">
                {% if share %}
                {% for user in share.allowed_users %}
                <span class="inline-flex items-center px-2 py-1 rounded-md text-sm bg-purple-100 text-purple-800">
                    {{ user }}
                    <button type="button" onclick="removeTag('allowed_users', '{{ user }}')" class="ml-1 text-purple-600 hover:text-purple-800">&times;</button>
                    <input type="hidden" name="allowed_users" value="{{ user }}">
                </span>
                {% endfor %}
                {% endif %}
            </div>
            <p class="mt-1 text-sm text-gray-500">Share will be accessible to these users in addition to you</p>
        </div>

        <!-- Submit -->
        <div class="flex justify-end gap-4">
            <a href="/ui/shares" class="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50">
                Cancel
            </a>
            <button type="submit"
                class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500">
                {{ 'Save Changes' if share else 'Create Share' }}
            </button>
        </div>
    </form>
</div>

<script>
function toggleDoneFolder(enabled) {
    document.getElementById('done-folder-options').classList.toggle('hidden', !enabled);
}

function addTag(field, tagName) {
    const chipsContainer = document.getElementById(field.replace('_', '-') + '-chips');
    const isSingle = field === 'done_tag';

    // For single-select, clear existing
    if (isSingle) {
        chipsContainer.innerHTML = '';
    }

    // Check if already added
    const existing = chipsContainer.querySelector(`input[value="${tagName}"]`);
    if (existing) return;

    const colorClass = {
        'include_tags': 'bg-blue-100 text-blue-800',
        'exclude_tags': 'bg-gray-100 text-gray-800',
        'done_tag': 'bg-green-100 text-green-800',
        'allowed_users': 'bg-purple-100 text-purple-800',
    }[field] || 'bg-gray-100 text-gray-800';

    const chip = document.createElement('span');
    chip.className = `inline-flex items-center px-2 py-1 rounded-md text-sm ${colorClass}`;
    chip.innerHTML = `
        ${tagName}
        <button type="button" onclick="removeTag('${field}', '${tagName}')" class="ml-1 hover:opacity-75">&times;</button>
        <input type="hidden" name="${field}" value="${tagName}">
    `;
    chipsContainer.appendChild(chip);

    // Clear input and hide suggestions
    const input = document.getElementById(field.replace('_', '-') + '-input');
    if (input) {
        input.value = '';
    }
    const suggestions = document.getElementById(field.replace('_', '-') + '-suggestions');
    if (suggestions) {
        suggestions.classList.add('hidden');
    }
}

function removeTag(field, tagName) {
    const chipsContainer = document.getElementById(field.replace('_', '-') + '-chips');
    const chip = chipsContainer.querySelector(`input[value="${tagName}"]`)?.parentElement;
    if (chip) {
        chip.remove();
    }
}
</script>
{% endblock %}
```

**Step 4: Add create/edit routes**

Add to `src/paperless_webdav/ui/routes.py`:

```python
async def get_share_by_name(session: AsyncSession, name: str, username: str):
    """Get share by name - wrapper for easy mocking."""
    return await share_service.get_share_by_name(session, name, username)


@router.get("/shares/new", response_class=HTMLResponse)
async def create_share_page(
    request: Request,
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)] = None,
) -> Response:
    """Render the create share form."""
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="shares/form.html",
        context={"share": None},
    )


@router.get("/shares/{name}/edit", response_class=HTMLResponse)
async def edit_share_page(
    request: Request,
    name: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)] = None,
) -> Response:
    """Render the edit share form."""
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    share = await get_share_by_name(session, name, current_user.username)
    if not share:
        return RedirectResponse(url="/ui/shares", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="shares/form.html",
        context={"share": share},
    )
```

**Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/paperless_webdav/ui/ tests/test_ui_routes.py
git commit -m "feat: add create/edit share form pages

- Create share form with all fields
- Edit share form pre-populated with data
- Tag autocomplete inputs with HTMX
- Done folder toggle with conditional fields
- JavaScript for chip add/remove

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Tag Autocomplete Partial

**Files:**
- Modify: `src/paperless_webdav/ui/routes.py`
- Create: `src/paperless_webdav/ui/templates/partials/tag_suggestions.html`
- Modify: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_ui_routes.py

@pytest.mark.asyncio
async def test_tag_suggestions_returns_matches(app, auth_cookie, mock_settings):
    """Tag suggestions should return matching tags from Paperless."""
    from paperless_webdav.ui import routes as ui_routes
    from paperless_webdav.paperless_client import PaperlessTag

    mock_tags = [
        PaperlessTag(id=1, name="invoices", slug="invoices", color="#ff0000"),
        PaperlessTag(id=2, name="income", slug="income", color="#00ff00"),
    ]

    with patch.object(ui_routes, "search_tags_from_paperless", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_tags

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/ui/partials/tag-suggestions",
                params={"q": "in", "field": "include_tags"},
                cookies={"session": auth_cookie},
            )

    assert response.status_code == 200
    assert "invoices" in response.text
    assert "income" in response.text
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_tag_suggestions_returns_matches -v`
Expected: FAIL (route not found)

**Step 3: Create tag suggestions partial**

```html
<!-- src/paperless_webdav/ui/templates/partials/tag_suggestions.html -->
{% if tags %}
<ul class="py-1">
    {% for tag in tags %}
    <li>
        <button type="button"
            onclick="addTag('{{ field }}', '{{ tag.name }}')"
            class="w-full px-4 py-2 text-left hover:bg-gray-100 flex items-center">
            {% if tag.color %}
            <span class="w-3 h-3 rounded-full mr-2" style="background-color: {{ tag.color }}"></span>
            {% endif %}
            {{ tag.name }}
        </button>
    </li>
    {% endfor %}
</ul>
{% else %}
<div class="px-4 py-2 text-gray-500 text-sm">No tags found</div>
{% endif %}
```

**Step 4: Create partials directory and add route**

Run: `mkdir -p src/paperless_webdav/ui/templates/partials`

Add to `src/paperless_webdav/ui/routes.py`:

```python
from paperless_webdav.paperless_client import PaperlessClient, PaperlessTag
from paperless_webdav.auth import get_current_user


async def search_tags_from_paperless(client: PaperlessClient, query: str) -> list[PaperlessTag]:
    """Search tags from Paperless - wrapper for easy mocking."""
    return await client.search_tags(query)


@router.get("/partials/tag-suggestions", response_class=HTMLResponse)
async def tag_suggestions(
    request: Request,
    q: str = "",
    field: str = "include_tags",
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> HTMLResponse:
    """Return tag suggestions for autocomplete."""
    if not q or len(q) < 1:
        return HTMLResponse("")

    client = PaperlessClient(base_url=settings.paperless_url, token=current_user.token)
    tags = await search_tags_from_paperless(client, q)

    return templates.TemplateResponse(
        request=request,
        name="partials/tag_suggestions.html",
        context={"tags": tags, "field": field},
    )
```

**Step 5: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_tag_suggestions_returns_matches -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/paperless_webdav/ui/ tests/test_ui_routes.py
git commit -m "feat: add tag autocomplete partial

- HTMX endpoint for tag suggestions
- Search Paperless API for matching tags
- Display tag name and color indicator
- Click to add tag to field

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: User Autocomplete with Fallback

**Files:**
- Modify: `src/paperless_webdav/paperless_client.py`
- Modify: `src/paperless_webdav/ui/routes.py`
- Create: `src/paperless_webdav/ui/templates/partials/user_suggestions.html`
- Modify: `tests/test_ui_routes.py`
- Modify: `tests/test_paperless_client.py`

**Step 1: Write the failing test for client**

```python
# Add to tests/test_paperless_client.py

@pytest.mark.asyncio
async def test_get_users(mock_paperless_url, mock_token):
    """Should return users from Paperless API."""
    users_data = {
        "results": [
            {"id": 1, "username": "alice", "first_name": "Alice", "last_name": "Smith"},
            {"id": 2, "username": "bob", "first_name": "Bob", "last_name": "Jones"},
        ],
        "next": None,
    }

    with respx.mock:
        respx.get(f"{mock_paperless_url}/api/users/").mock(
            return_value=httpx.Response(200, json=users_data)
        )

        client = PaperlessClient(mock_paperless_url, mock_token)
        users = await client.get_users()

    assert len(users) == 2
    assert users[0].username == "alice"
    assert users[1].username == "bob"


@pytest.mark.asyncio
async def test_get_users_permission_denied(mock_paperless_url, mock_token):
    """Should return empty list on 403."""
    with respx.mock:
        respx.get(f"{mock_paperless_url}/api/users/").mock(
            return_value=httpx.Response(403, json={"detail": "Permission denied"})
        )

        client = PaperlessClient(mock_paperless_url, mock_token)
        users = await client.get_users()

    assert users == []
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_paperless_client.py::test_get_users -v`
Expected: FAIL (method not found)

**Step 3: Add user methods to PaperlessClient**

Add to `src/paperless_webdav/paperless_client.py`:

```python
@dataclass(frozen=True)
class PaperlessUser:
    """Represents a user in Paperless-ngx."""

    id: int
    username: str
    first_name: str = ""
    last_name: str = ""

    @property
    def display_name(self) -> str:
        """Return display name (full name or username)."""
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.username
```

Add methods to `PaperlessClient` class:

```python
    async def get_users(self) -> list[PaperlessUser]:
        """Fetch all users from Paperless-ngx.

        Returns empty list if user lacks permission (403).

        Returns:
            List of PaperlessUser objects
        """
        try:
            results = await self._paginated_get("/api/users/")
            users = [
                PaperlessUser(
                    id=user["id"],
                    username=user["username"],
                    first_name=user.get("first_name", ""),
                    last_name=user.get("last_name", ""),
                )
                for user in results
            ]
            logger.debug("fetched_users", count=len(users))
            return users
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.debug("users_permission_denied")
                return []
            raise

    async def search_users(self, name_filter: str) -> list[PaperlessUser]:
        """Search users by username or name.

        Returns empty list if user lacks permission (403).

        Args:
            name_filter: Partial name to search for

        Returns:
            List of matching PaperlessUser objects
        """
        try:
            results = await self._paginated_get(
                "/api/users/",
                params={"username__icontains": name_filter},
            )
            users = [
                PaperlessUser(
                    id=user["id"],
                    username=user["username"],
                    first_name=user.get("first_name", ""),
                    last_name=user.get("last_name", ""),
                )
                for user in results
            ]
            logger.debug("searched_users", filter=name_filter, count=len(users))
            return users
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.debug("users_search_permission_denied")
                return []
            raise
```

**Step 4: Run client tests**

Run: `source .venv/bin/activate && pytest tests/test_paperless_client.py -v`
Expected: All PASS

**Step 5: Create user suggestions partial**

```html
<!-- src/paperless_webdav/ui/templates/partials/user_suggestions.html -->
{% if users %}
<ul class="py-1">
    {% for user in users %}
    <li>
        <button type="button"
            onclick="addTag('allowed_users', '{{ user.username }}')"
            class="w-full px-4 py-2 text-left hover:bg-gray-100">
            <span class="font-medium">{{ user.username }}</span>
            {% if user.display_name != user.username %}
            <span class="text-gray-500 ml-2">{{ user.display_name }}</span>
            {% endif %}
        </button>
    </li>
    {% endfor %}
</ul>
{% elif fallback %}
<div class="px-4 py-2 text-gray-500 text-sm">
    Enter usernames manually, separated by commas
</div>
{% else %}
<div class="px-4 py-2 text-gray-500 text-sm">No users found</div>
{% endif %}
```

**Step 6: Add user suggestions route**

Add to `src/paperless_webdav/ui/routes.py`:

```python
from paperless_webdav.paperless_client import PaperlessUser


async def search_users_from_paperless(client: PaperlessClient, query: str) -> list[PaperlessUser] | None:
    """Search users from Paperless - returns None if no permission."""
    users = await client.search_users(query)
    # Empty list from search_users means either no results or no permission
    # Try get_users to check permission
    if not users:
        all_users = await client.get_users()
        if not all_users:
            return None  # No permission
    return users


@router.get("/partials/user-suggestions", response_class=HTMLResponse)
async def user_suggestions(
    request: Request,
    q: str = "",
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> HTMLResponse:
    """Return user suggestions for autocomplete."""
    if not q or len(q) < 1:
        return HTMLResponse("")

    client = PaperlessClient(base_url=settings.paperless_url, token=current_user.token)
    users = await search_users_from_paperless(client, q)

    return templates.TemplateResponse(
        request=request,
        name="partials/user_suggestions.html",
        context={
            "users": users if users is not None else [],
            "fallback": users is None,
        },
    )
```

**Step 7: Run all tests**

Run: `source .venv/bin/activate && pytest tests/ -v`
Expected: All PASS

**Step 8: Commit**

```bash
git add src/paperless_webdav/ tests/
git commit -m "feat: add user autocomplete with permission fallback

- Add PaperlessUser dataclass and get_users/search_users methods
- Return empty list on 403 (no permission)
- User suggestions partial with fallback message
- Display username and full name in suggestions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Form Submission Handlers

**Files:**
- Modify: `src/paperless_webdav/ui/routes.py`
- Modify: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_ui_routes.py

@pytest.mark.asyncio
async def test_create_share_submit(app, auth_cookie, mock_settings):
    """Create share form submission should create share and redirect."""
    from paperless_webdav.ui import routes as ui_routes

    with patch.object(ui_routes, "create_share_in_db", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = type("Share", (), {"id": "test-id", "name": "new-share"})()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/ui/shares/new",
                data={
                    "name": "new-share",
                    "include_tags": ["tag1", "tag2"],
                    "read_only": "true",
                },
                cookies={"session": auth_cookie},
                follow_redirects=False,
            )

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/shares"
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_update_share_submit(app, auth_cookie, mock_settings):
    """Update share form submission should update and redirect."""
    from paperless_webdav.ui import routes as ui_routes
    from uuid import uuid4

    mock_share = type("Share", (), {"id": uuid4(), "name": "test-share"})()

    with patch.object(ui_routes, "get_share_by_name", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_share

        with patch.object(ui_routes, "update_share_in_db", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = mock_share

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/ui/shares/test-share/edit",
                    data={
                        "name": "test-share",
                        "include_tags": ["updated-tag"],
                        "read_only": "true",
                    },
                    cookies={"session": auth_cookie},
                    follow_redirects=False,
                )

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/shares"
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_create_share_submit -v`
Expected: FAIL (POST handler not found)

**Step 3: Add form submission handlers**

Add to `src/paperless_webdav/ui/routes.py`:

```python
from datetime import datetime
from paperless_webdav.schemas import ShareCreate, ShareUpdate


async def create_share_in_db(session: AsyncSession, username: str, data: ShareCreate):
    """Create share in database - wrapper for easy mocking."""
    return await share_service.create_share(session, username, data)


async def update_share_in_db(session: AsyncSession, share_id, data: ShareUpdate):
    """Update share in database - wrapper for easy mocking."""
    return await share_service.update_share(session, share_id, data)


def _parse_form_data(form_data: dict) -> dict:
    """Parse form data into share fields."""
    # Handle multi-value fields (tags come as list or single value)
    include_tags = form_data.getlist("include_tags") if hasattr(form_data, "getlist") else form_data.get("include_tags", [])
    exclude_tags = form_data.getlist("exclude_tags") if hasattr(form_data, "getlist") else form_data.get("exclude_tags", [])
    allowed_users = form_data.getlist("allowed_users") if hasattr(form_data, "getlist") else form_data.get("allowed_users", [])

    # Ensure lists
    if isinstance(include_tags, str):
        include_tags = [include_tags] if include_tags else []
    if isinstance(exclude_tags, str):
        exclude_tags = [exclude_tags] if exclude_tags else []
    if isinstance(allowed_users, str):
        allowed_users = [allowed_users] if allowed_users else []

    # Parse datetime
    expires_at = None
    if form_data.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(form_data["expires_at"])
        except ValueError:
            pass

    return {
        "name": form_data.get("name", ""),
        "include_tags": include_tags,
        "exclude_tags": exclude_tags,
        "read_only": form_data.get("read_only") == "true",
        "done_folder_enabled": form_data.get("done_folder_enabled") == "true",
        "done_folder_name": form_data.get("done_folder_name", "done"),
        "done_tag": form_data.get("done_tag") or None,
        "expires_at": expires_at,
        "allowed_users": allowed_users,
    }


@router.post("/shares/new")
async def create_share_submit(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)] = None,
) -> Response:
    """Handle create share form submission."""
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    form_data = await request.form()
    parsed = _parse_form_data(form_data)

    try:
        share_data = ShareCreate(**parsed)
        await create_share_in_db(session, current_user.username, share_data)
        return RedirectResponse(url="/ui/shares", status_code=303)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request,
            name="shares/form.html",
            context={"share": None, "error": str(e)},
        )


@router.post("/shares/{name}/edit")
async def update_share_submit(
    request: Request,
    name: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser | None, Depends(get_current_user_optional)] = None,
) -> Response:
    """Handle edit share form submission."""
    if current_user is None:
        return RedirectResponse(url="/ui/login", status_code=303)

    share = await get_share_by_name(session, name, current_user.username)
    if not share:
        return RedirectResponse(url="/ui/shares", status_code=303)

    form_data = await request.form()
    parsed = _parse_form_data(form_data)

    # Remove name from update data
    del parsed["name"]

    try:
        share_data = ShareUpdate(**parsed)
        await update_share_in_db(session, share.id, share_data)
        return RedirectResponse(url="/ui/shares", status_code=303)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request,
            name="shares/form.html",
            context={"share": share, "error": str(e)},
        )
```

**Step 4: Run tests**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/ui/ tests/test_ui_routes.py
git commit -m "feat: add share form submission handlers

- POST /ui/shares/new creates share
- POST /ui/shares/{name}/edit updates share
- Parse multi-value form fields (tags, users)
- Validation errors displayed on form

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Delete Share Handler

**Files:**
- Modify: `src/paperless_webdav/ui/routes.py`
- Modify: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_ui_routes.py

@pytest.mark.asyncio
async def test_delete_share(app, auth_cookie, mock_settings):
    """Delete share should remove and return empty response."""
    from paperless_webdav.ui import routes as ui_routes

    with patch.object(ui_routes, "delete_share_from_db", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = True

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                "/ui/shares/test-share",
                cookies={"session": auth_cookie},
            )

    assert response.status_code == 200
    assert response.text == ""  # Empty response for HTMX to remove row
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_delete_share -v`
Expected: FAIL (DELETE handler not found)

**Step 3: Add delete handler**

Add to `src/paperless_webdav/ui/routes.py`:

```python
async def delete_share_from_db(session: AsyncSession, name: str, username: str) -> bool:
    """Delete share from database - wrapper for easy mocking."""
    return await share_service.delete_share(session, name, username)


@router.delete("/shares/{name}")
async def delete_share(
    name: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Response:
    """Delete a share."""
    deleted = await delete_share_from_db(session, name, current_user.username)
    if not deleted:
        return Response(status_code=404)
    return Response(status_code=200, content="")
```

**Step 4: Run test**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_delete_share -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/ui/ tests/test_ui_routes.py
git commit -m "feat: add share delete handler for HTMX

- DELETE /ui/shares/{name} removes share
- Returns empty response for HTMX row removal
- Returns 404 if share not found

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Logout Handler

**Files:**
- Modify: `src/paperless_webdav/ui/routes.py`
- Modify: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_ui_routes.py

@pytest.mark.asyncio
async def test_logout_clears_session_and_redirects(app, auth_cookie, mock_settings):
    """Logout should clear session and redirect to login."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/ui/logout",
            cookies={"session": auth_cookie},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"
    # Cookie should be cleared (max_age=0)
    assert "session=" in response.headers.get("set-cookie", "")
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_logout_clears_session_and_redirects -v`
Expected: FAIL (route not found)

**Step 3: Add logout handler**

Add to `src/paperless_webdav/ui/routes.py`:

```python
@router.post("/logout")
async def logout() -> Response:
    """Clear session and redirect to login."""
    response = RedirectResponse(url="/ui/login", status_code=303)
    response.set_cookie(
        key="session",
        value="",
        httponly=True,
        samesite="lax",
        max_age=0,
    )
    return response
```

**Step 4: Run test**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_logout_clears_session_and_redirects -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/ui/ tests/test_ui_routes.py
git commit -m "feat: add logout handler

- POST /ui/logout clears session cookie
- Redirects to login page

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Final Integration Test

**Files:**
- Modify: `tests/test_ui_routes.py`

**Step 1: Write integration test**

```python
# Add to tests/test_ui_routes.py

@pytest.mark.asyncio
async def test_full_share_crud_flow(app, mock_settings):
    """Test complete flow: login -> create -> edit -> delete -> logout."""
    from paperless_webdav.ui import routes as ui_routes

    # Mock Paperless auth
    with patch("paperless_webdav.ui.routes.httpx.AsyncClient") as mock_http:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "test-token"}
        mock_http.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Login
            login_response = await client.post(
                "/ui/login",
                data={"username": "testuser", "password": "testpass"},
                follow_redirects=False,
            )
            assert login_response.status_code == 303
            session_cookie = login_response.cookies.get("session")
            assert session_cookie is not None

            # 2. View shares list (empty)
            with patch.object(ui_routes, "get_user_shares", new_callable=AsyncMock) as mock_shares:
                mock_shares.return_value = []
                list_response = await client.get("/ui/shares")
                assert list_response.status_code == 200
                assert "Your Shares" in list_response.text

            # 3. View create form
            create_page = await client.get("/ui/shares/new")
            assert create_page.status_code == 200
            assert "Create Share" in create_page.text

            # 4. Logout
            logout_response = await client.post("/ui/logout", follow_redirects=False)
            assert logout_response.status_code == 303
            assert logout_response.headers["location"] == "/ui/login"
```

**Step 2: Run integration test**

Run: `source .venv/bin/activate && pytest tests/test_ui_routes.py::test_full_share_crud_flow -v`
Expected: PASS

**Step 3: Run all tests**

Run: `source .venv/bin/activate && pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tests/test_ui_routes.py
git commit -m "test: add integration test for full share CRUD flow

- Test login -> list -> create form -> logout flow
- Verify session cookie handling throughout

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

After completing all tasks, you will have:

1. **Login page** - Username/password form with Paperless authentication
2. **Share list page** - Table of user's shares with edit/delete actions
3. **Create/Edit form** - Full share configuration with tag autocomplete
4. **Tag autocomplete** - HTMX-powered search with chip selection
5. **User autocomplete** - With fallback for non-admin users
6. **CRUD handlers** - Create, update, delete shares via form posts
7. **Logout** - Clear session and redirect

All routes protected by authentication, redirecting to login when needed.
