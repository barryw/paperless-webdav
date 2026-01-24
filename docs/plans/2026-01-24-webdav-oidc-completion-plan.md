# WebDAV Integration, Done Folder & OIDC Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the paperless-webdav service so it actually serves documents via WebDAV, supports OIDC authentication (Authentik), and implements the done folder workflow.

**Architecture:** The WebDAV provider (wsgidav) needs to be wired to the database to load shares, and to the Paperless client to fetch documents. A separate Cheroot server runs wsgidav on port 8081 alongside the FastAPI admin UI on 8080. OIDC users authenticate via Authentik, then manually enter their Paperless API token (stored encrypted in database).

**Tech Stack:** wsgidav, cheroot, authlib (OIDC), asyncio for sync/async bridging

---

## Phase 1: WebDAV Provider Integration

### Task 1.1: Add Async Bridge for wsgidav

wsgidav is synchronous but our Paperless client is async. We need a bridge.

**Files:**
- Create: `src/paperless_webdav/async_bridge.py`
- Test: `tests/test_async_bridge.py`

**Step 1: Write the failing test**

```python
# tests/test_async_bridge.py
"""Tests for async/sync bridge utilities."""

import asyncio
import pytest
from paperless_webdav.async_bridge import run_async


def test_run_async_returns_result():
    """run_async should execute coroutine and return result."""
    async def coro():
        return "hello"

    result = run_async(coro())
    assert result == "hello"


def test_run_async_propagates_exceptions():
    """run_async should propagate exceptions from coroutine."""
    async def failing_coro():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        run_async(failing_coro())


def test_run_async_works_from_sync_context():
    """run_async should work when no event loop is running."""
    async def fetch_data():
        await asyncio.sleep(0.001)
        return {"data": 42}

    result = run_async(fetch_data())
    assert result == {"data": 42}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/barry/paperless-webdav/.worktrees/dev && source .venv/bin/activate && pytest tests/test_async_bridge.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/paperless_webdav/async_bridge.py
"""Bridge utilities for running async code from sync contexts.

wsgidav is synchronous, but our Paperless client is async.
This module provides utilities to bridge the two.
"""

import asyncio
from typing import TypeVar

T = TypeVar("T")


def run_async(coro: asyncio.coroutines) -> T:
    """Run an async coroutine from a synchronous context.

    Creates a new event loop if none exists, or uses asyncio.run().
    This is safe to call from wsgidav request handlers.

    Args:
        coro: The coroutine to execute

    Returns:
        The result of the coroutine
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop - create one
        return asyncio.run(coro)

    # If there's a running loop, we need to run in a new thread
    # This shouldn't happen in normal wsgidav usage, but handle it
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_async_bridge.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/async_bridge.py tests/test_async_bridge.py
git commit -m "feat: add async/sync bridge for wsgidav integration"
```

---

### Task 1.2: Wire WebDAV Provider to Load Documents from Paperless

Update the WebDAV provider to actually fetch documents from Paperless.

**Files:**
- Modify: `src/paperless_webdav/webdav_provider.py`
- Modify: `tests/test_webdav_provider.py`

**Step 1: Write failing tests**

Add to `tests/test_webdav_provider.py`:

```python
@pytest.mark.asyncio
async def test_share_resource_loads_documents_from_paperless():
    """ShareResource should load documents from Paperless API."""
    mock_share = MagicMock()
    mock_share.name = "tax2025"
    mock_share.include_tags = ["tax", "2025"]
    mock_share.exclude_tags = []
    mock_share.done_folder_enabled = False
    mock_share.done_tag = None

    mock_client = MagicMock()
    mock_client.get_tags = AsyncMock(return_value=[
        PaperlessTag(id=1, name="tax", slug="tax"),
        PaperlessTag(id=2, name="2025", slug="2025"),
    ])
    mock_client.get_documents = AsyncMock(return_value=[
        PaperlessDocument(
            id=42,
            title="W2 Form",
            original_file_name="w2.pdf",
            created="2025-01-15T10:00:00Z",
            modified="2025-01-15T10:00:00Z",
            tags=[1, 2],
        ),
    ])

    resource = ShareResource("/tax2025", {
        "share": mock_share,
        "paperless_client": mock_client,
        "tag_cache": {},
    })

    # This should trigger document loading
    members = resource.get_member_names()

    assert "W2 Form.pdf" in members
    mock_client.get_documents.assert_called_once()


@pytest.mark.asyncio
async def test_document_resource_downloads_content():
    """DocumentResource should download content from Paperless."""
    mock_doc = PaperlessDocument(
        id=42,
        title="W2 Form",
        original_file_name="w2.pdf",
        created="2025-01-15T10:00:00Z",
        modified="2025-01-15T10:00:00Z",
        tags=[1, 2],
    )

    mock_client = MagicMock()
    mock_client.download_document = AsyncMock(return_value=b"%PDF-1.4 fake content")

    resource = DocumentResource("/tax2025/W2 Form.pdf", {
        "document": mock_doc,
        "paperless_client": mock_client,
    })

    content = resource.get_content()

    assert content.read().startswith(b"%PDF")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_webdav_provider.py::test_share_resource_loads_documents_from_paperless -v`
Expected: FAIL (documents not loaded)

**Step 3: Update webdav_provider.py**

Update the `ShareResource._load_documents()` and `DocumentResource.get_content()` methods to actually use the Paperless client. Key changes:

1. `ShareResource.__init__` stores paperless_client and tag_cache
2. `ShareResource._load_documents()` calls `run_async(self._fetch_documents())`
3. `ShareResource._fetch_documents()` is async - resolves tag names to IDs, fetches documents
4. `DocumentResource.get_content()` calls `run_async(client.download_document(id))`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_webdav_provider.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/webdav_provider.py tests/test_webdav_provider.py
git commit -m "feat: wire WebDAV provider to fetch documents from Paperless API"
```

---

### Task 1.3: Create WebDAV Authentication via HTTP Basic Auth

WebDAV clients use HTTP Basic Auth. We need to validate against Paperless.

**Files:**
- Create: `src/paperless_webdav/webdav_auth.py`
- Create: `tests/test_webdav_auth.py`

**Step 1: Write the failing test**

```python
# tests/test_webdav_auth.py
"""Tests for WebDAV HTTP Basic authentication."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from paperless_webdav.webdav_auth import PaperlessBasicAuthenticator


@pytest.fixture
def authenticator(mock_settings):
    """Create authenticator instance."""
    return PaperlessBasicAuthenticator("http://paperless.test")


def test_authenticator_returns_username_on_valid_credentials(authenticator):
    """Valid credentials should return username."""
    with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
        mock_run.return_value = ("test-token-123", None)

        result = authenticator.authenticate("http://test", {"username": "barry", "password": "secret"})

        assert result == "barry"


def test_authenticator_returns_false_on_invalid_credentials(authenticator):
    """Invalid credentials should return False."""
    with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
        mock_run.return_value = (None, "Invalid credentials")

        result = authenticator.authenticate("http://test", {"username": "barry", "password": "wrong"})

        assert result is False


def test_authenticator_stores_token_for_user(authenticator):
    """Authenticator should store token for later use."""
    with patch("paperless_webdav.webdav_auth.run_async") as mock_run:
        mock_run.return_value = ("test-token-123", None)

        authenticator.authenticate("http://test", {"username": "barry", "password": "secret"})

        assert authenticator.get_token("barry") == "test-token-123"


def test_authenticator_is_wsgidav_compatible(authenticator):
    """Authenticator should implement wsgidav interface."""
    # wsgidav calls these methods
    assert hasattr(authenticator, "authenticate")
    assert hasattr(authenticator, "supports_http_digest_auth")
    assert authenticator.supports_http_digest_auth() is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_webdav_auth.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/paperless_webdav/webdav_auth.py
"""HTTP Basic authentication for WebDAV using Paperless credentials."""

from typing import Any

from wsgidav.dc.base_dc import BaseDomainController

from paperless_webdav.async_bridge import run_async
from paperless_webdav.auth.paperless import _authenticate_with_paperless
from paperless_webdav.logging import get_logger

logger = get_logger(__name__)


class PaperlessBasicAuthenticator(BaseDomainController):
    """wsgidav domain controller that authenticates against Paperless.

    Validates HTTP Basic Auth credentials by calling the Paperless
    /api/token/ endpoint. Stores the returned token for use by
    the WebDAV provider when fetching documents.
    """

    def __init__(self, paperless_url: str) -> None:
        super().__init__(None)
        self._paperless_url = paperless_url
        self._user_tokens: dict[str, str] = {}

    def get_domain_realm(self, path_info: str, environ: dict) -> str:
        """Return the authentication realm."""
        return "Paperless WebDAV"

    def require_authentication(self, realm: str, environ: dict) -> bool:
        """Always require authentication for WebDAV."""
        return True

    def supports_http_digest_auth(self) -> bool:
        """We only support Basic auth (need password to get token)."""
        return False

    def basic_auth_user(self, realm: str, username: str, password: str, environ: dict) -> bool | str:
        """Authenticate user with Basic auth credentials.

        Args:
            realm: Authentication realm
            username: Username from Basic auth header
            password: Password from Basic auth header
            environ: WSGI environ dict

        Returns:
            Username string if authenticated, False otherwise
        """
        token, error = run_async(
            _authenticate_with_paperless(username, password, self._paperless_url)
        )

        if error is not None:
            logger.info("webdav_auth_failed", username=username, error=error)
            return False

        # Store token for later use
        self._user_tokens[username] = token
        environ["paperless.username"] = username
        environ["paperless.token"] = token

        logger.info("webdav_auth_success", username=username)
        return username

    # Alias for wsgidav compatibility
    def authenticate(self, realm: str, credentials: dict[str, Any]) -> bool | str:
        """wsgidav-compatible authenticate method."""
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        return self.basic_auth_user(realm, username, password, {})

    def get_token(self, username: str) -> str | None:
        """Get stored token for a user."""
        return self._user_tokens.get(username)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_webdav_auth.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/webdav_auth.py tests/test_webdav_auth.py
git commit -m "feat: add WebDAV HTTP Basic auth against Paperless"
```

---

### Task 1.4: Create WebDAV Server with Cheroot

**Files:**
- Create: `src/paperless_webdav/webdav_server.py`
- Create: `tests/test_webdav_server.py`

**Step 1: Write the failing test**

```python
# tests/test_webdav_server.py
"""Tests for WebDAV server setup."""

import pytest
from unittest.mock import MagicMock, patch

from paperless_webdav.webdav_server import create_webdav_app, WebDAVServer


def test_create_webdav_app_returns_wsgi_app(mock_settings):
    """create_webdav_app should return a WSGI application."""
    with patch("paperless_webdav.webdav_server.PaperlessBasicAuthenticator"):
        app = create_webdav_app(
            paperless_url="http://paperless.test",
            share_loader=lambda: {},
        )

    # WSGI apps are callable
    assert callable(app)


def test_webdav_server_starts_on_configured_port(mock_settings):
    """WebDAV server should bind to configured port."""
    with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server") as mock_server:
        mock_server_instance = MagicMock()
        mock_server.return_value = mock_server_instance

        server = WebDAVServer(
            host="0.0.0.0",
            port=8081,
            paperless_url="http://paperless.test",
            share_loader=lambda: {},
        )

        mock_server.assert_called_once()
        call_args = mock_server.call_args
        assert call_args[0][0] == ("0.0.0.0", 8081)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_webdav_server.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/paperless_webdav/webdav_server.py
"""WebDAV server using wsgidav and cheroot."""

from typing import Any, Callable

import cheroot.wsgi
from wsgidav.wsgidav_app import WsgiDAVApp

from paperless_webdav.webdav_auth import PaperlessBasicAuthenticator
from paperless_webdav.webdav_provider import PaperlessProvider
from paperless_webdav.logging import get_logger

logger = get_logger(__name__)


def create_webdav_app(
    paperless_url: str,
    share_loader: Callable[[], dict[str, Any]],
) -> WsgiDAVApp:
    """Create the wsgidav WSGI application.

    Args:
        paperless_url: Base URL of Paperless-ngx
        share_loader: Callable that returns dict of share configs

    Returns:
        Configured WsgiDAVApp instance
    """
    provider = PaperlessProvider()

    # Create authenticator
    authenticator = PaperlessBasicAuthenticator(paperless_url)

    config = {
        "provider_mapping": {"/": provider},
        "http_authenticator": {
            "domain_controller": authenticator,
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
        },
        "simple_dc": {"user_mapping": {}},  # Not used, but required
        "verbose": 1,
        "logging": {
            "enable": True,
            "enable_loggers": [],
        },
        # Store references for request handlers
        "paperless_url": paperless_url,
        "share_loader": share_loader,
        "authenticator": authenticator,
    }

    app = WsgiDAVApp(config)
    return app


class WebDAVServer:
    """Cheroot-based WebDAV server."""

    def __init__(
        self,
        host: str,
        port: int,
        paperless_url: str,
        share_loader: Callable[[], dict[str, Any]],
    ) -> None:
        """Initialize the WebDAV server.

        Args:
            host: Host to bind to
            port: Port to bind to
            paperless_url: Base URL of Paperless-ngx
            share_loader: Callable that returns dict of share configs
        """
        self._app = create_webdav_app(paperless_url, share_loader)
        self._server = cheroot.wsgi.Server(
            (host, port),
            self._app,
        )
        self._host = host
        self._port = port

    def start(self) -> None:
        """Start the WebDAV server (blocking)."""
        logger.info("webdav_server_starting", host=self._host, port=self._port)
        self._server.start()

    def stop(self) -> None:
        """Stop the WebDAV server."""
        logger.info("webdav_server_stopping")
        self._server.stop()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_webdav_server.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/webdav_server.py tests/test_webdav_server.py
git commit -m "feat: add WebDAV server with cheroot"
```

---

### Task 1.5: Create Main Entrypoint Running Both Servers

**Files:**
- Create: `src/paperless_webdav/main.py`
- Create: `tests/test_main.py`

**Step 1: Write the failing test**

```python
# tests/test_main.py
"""Tests for main entrypoint."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def test_load_shares_from_database(mock_settings):
    """load_shares should fetch shares from database."""
    from paperless_webdav.main import load_shares_sync

    with patch("paperless_webdav.main.run_async") as mock_run:
        mock_shares = [
            MagicMock(name="tax2025", include_tags=["tax"]),
            MagicMock(name="receipts", include_tags=["receipt"]),
        ]
        mock_run.return_value = mock_shares

        shares = load_shares_sync()

        assert "tax2025" in shares
        assert "receipts" in shares


def test_main_starts_both_servers(mock_settings):
    """main should start both FastAPI and WebDAV servers."""
    with patch("paperless_webdav.main.uvicorn") as mock_uvicorn:
        with patch("paperless_webdav.main.WebDAVServer") as mock_webdav:
            with patch("paperless_webdav.main.threading.Thread") as mock_thread:
                mock_thread_instance = MagicMock()
                mock_thread.return_value = mock_thread_instance

                # Import here to avoid side effects
                from paperless_webdav.main import run_servers

                # This would normally block, so we just check setup
                # In real test, we'd use a timeout or mock the blocking call
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/paperless_webdav/main.py
"""Main entrypoint for running both Admin UI and WebDAV servers."""

import asyncio
import signal
import sys
import threading
from typing import Any

import uvicorn

from paperless_webdav.async_bridge import run_async
from paperless_webdav.config import get_settings
from paperless_webdav.database import init_database, close_database, get_session
from paperless_webdav.logging import setup_logging, get_logger
from paperless_webdav.models import Share
from paperless_webdav.webdav_server import WebDAVServer

logger = get_logger(__name__)


async def _load_all_shares() -> list[Share]:
    """Load all shares from database."""
    from sqlalchemy import select
    from paperless_webdav.database import _async_session_factory

    if _async_session_factory is None:
        return []

    async with _async_session_factory() as session:
        result = await session.execute(select(Share))
        return list(result.scalars().all())


def load_shares_sync() -> dict[str, Any]:
    """Load shares synchronously for WebDAV provider.

    Returns:
        Dict mapping share names to Share objects
    """
    shares = run_async(_load_all_shares())
    return {share.name: share for share in shares}


def run_servers() -> None:
    """Run both Admin UI (FastAPI) and WebDAV servers."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)

    logger.info(
        "starting_servers",
        admin_port=settings.admin_port,
        webdav_port=settings.webdav_port,
    )

    # Initialize database synchronously before starting servers
    run_async(init_database(settings.database_url.get_secret_value()))

    # Create WebDAV server
    webdav_server = WebDAVServer(
        host="0.0.0.0",
        port=settings.webdav_port,
        paperless_url=settings.paperless_url,
        share_loader=load_shares_sync,
    )

    # Run WebDAV server in background thread
    webdav_thread = threading.Thread(target=webdav_server.start, daemon=True)
    webdav_thread.start()
    logger.info("webdav_server_started", port=settings.webdav_port)

    # Handle shutdown signals
    def shutdown(signum, frame):
        logger.info("shutdown_signal_received", signal=signum)
        webdav_server.stop()
        run_async(close_database())
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Run FastAPI in main thread (blocking)
    uvicorn.run(
        "paperless_webdav.app:app",
        host="0.0.0.0",
        port=settings.admin_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run_servers()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/main.py tests/test_main.py
git commit -m "feat: add main entrypoint running both servers"
```

---

## Phase 2: Done Folder Feature

### Task 2.1: Filter Root Listing to Exclude Done Documents

Documents with the done_tag should not appear in the share root (they appear in done folder only).

**Files:**
- Modify: `src/paperless_webdav/webdav_provider.py`
- Modify: `tests/test_webdav_provider.py`

**Step 1: Write the failing test**

Add to `tests/test_webdav_provider.py`:

```python
def test_share_resource_excludes_done_documents_from_root():
    """Root listing should exclude documents with done_tag."""
    mock_share = MagicMock()
    mock_share.name = "inbox"
    mock_share.include_tags = ["inbox"]
    mock_share.exclude_tags = []
    mock_share.done_folder_enabled = True
    mock_share.done_folder_name = "processed"
    mock_share.done_tag = "processed"

    # Two documents: one without done_tag, one with
    mock_client = MagicMock()
    mock_client.get_tags = AsyncMock(return_value=[
        PaperlessTag(id=1, name="inbox", slug="inbox"),
        PaperlessTag(id=2, name="processed", slug="processed"),
    ])
    mock_client.get_documents = AsyncMock(return_value=[
        PaperlessDocument(id=1, title="New Doc", original_file_name="new.pdf",
                         created="2025-01-15T10:00:00Z", modified="2025-01-15T10:00:00Z",
                         tags=[1]),  # Only inbox tag
        PaperlessDocument(id=2, title="Done Doc", original_file_name="done.pdf",
                         created="2025-01-15T10:00:00Z", modified="2025-01-15T10:00:00Z",
                         tags=[1, 2]),  # Has processed tag
    ])

    resource = ShareResource("/inbox", {
        "share": mock_share,
        "paperless_client": mock_client,
        "tag_cache": {},
    })

    members = resource.get_member_names()

    # Root should only have "New Doc.pdf" and the "processed" folder
    assert "New Doc.pdf" in members
    assert "Done Doc.pdf" not in members
    assert "processed" in members
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_webdav_provider.py::test_share_resource_excludes_done_documents_from_root -v`
Expected: FAIL

**Step 3: Update implementation**

In `ShareResource._load_documents()`, filter out documents that have the done_tag when done_folder_enabled.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_webdav_provider.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/webdav_provider.py tests/test_webdav_provider.py
git commit -m "feat: filter done documents from share root listing"
```

---

### Task 2.2: Show Done Documents in Done Folder

**Files:**
- Modify: `src/paperless_webdav/webdav_provider.py`
- Modify: `tests/test_webdav_provider.py`

**Step 1: Write the failing test**

```python
def test_done_folder_shows_only_done_documents():
    """Done folder should only show documents with done_tag."""
    mock_share = MagicMock()
    mock_share.name = "inbox"
    mock_share.include_tags = ["inbox"]
    mock_share.exclude_tags = []
    mock_share.done_folder_enabled = True
    mock_share.done_folder_name = "processed"
    mock_share.done_tag = "processed"

    mock_client = MagicMock()
    mock_client.get_tags = AsyncMock(return_value=[
        PaperlessTag(id=1, name="inbox", slug="inbox"),
        PaperlessTag(id=2, name="processed", slug="processed"),
    ])
    # Only fetch documents with done tag for done folder
    mock_client.get_documents = AsyncMock(return_value=[
        PaperlessDocument(id=2, title="Done Doc", original_file_name="done.pdf",
                         created="2025-01-15T10:00:00Z", modified="2025-01-15T10:00:00Z",
                         tags=[1, 2]),
    ])

    resource = DoneFolderResource("/inbox/processed", {
        "share": mock_share,
        "paperless_client": mock_client,
        "tag_cache": {},
    })

    members = resource.get_member_names()

    assert "Done Doc.pdf" in members
```

**Step 2-5: Similar to previous task**

**Step 5: Commit**

```bash
git commit -m "feat: show done documents in done folder"
```

---

### Task 2.3: MOVE from Root to Done Folder (Add Tag)

**Files:**
- Modify: `src/paperless_webdav/webdav_provider.py`
- Modify: `tests/test_webdav_provider.py`

**Step 1: Write the failing test**

```python
def test_move_to_done_folder_adds_done_tag():
    """Moving doc from root to done folder should add done_tag."""
    mock_share = MagicMock()
    mock_share.name = "inbox"
    mock_share.done_folder_enabled = True
    mock_share.done_folder_name = "done"
    mock_share.done_tag = "processed"

    mock_doc = PaperlessDocument(
        id=42, title="Doc", original_file_name="doc.pdf",
        created="2025-01-15T10:00:00Z", modified="2025-01-15T10:00:00Z",
        tags=[1],
    )

    mock_client = MagicMock()
    mock_client.add_tag_to_document = AsyncMock()

    resource = DocumentResource("/inbox/Doc.pdf", {
        "document": mock_doc,
        "paperless_client": mock_client,
        "share": mock_share,
        "tag_cache": {"processed": 2},
    })

    # Simulate MOVE to /inbox/done/Doc.pdf
    resource.move("/inbox/done/Doc.pdf")

    mock_client.add_tag_to_document.assert_called_once_with(42, 2)
```

**Step 2-5: Similar pattern**

**Step 5: Commit**

```bash
git commit -m "feat: MOVE to done folder adds done_tag"
```

---

### Task 2.4: MOVE from Done Folder to Root (Remove Tag)

**Files:**
- Modify: `src/paperless_webdav/webdav_provider.py`
- Modify: `tests/test_webdav_provider.py`

**Step 1: Write the failing test**

```python
def test_move_from_done_folder_removes_done_tag():
    """Moving doc from done folder to root should remove done_tag."""
    mock_share = MagicMock()
    mock_share.name = "inbox"
    mock_share.done_folder_enabled = True
    mock_share.done_folder_name = "done"
    mock_share.done_tag = "processed"

    mock_doc = PaperlessDocument(
        id=42, title="Doc", original_file_name="doc.pdf",
        created="2025-01-15T10:00:00Z", modified="2025-01-15T10:00:00Z",
        tags=[1, 2],  # Has done tag
    )

    mock_client = MagicMock()
    mock_client.remove_tag_from_document = AsyncMock()

    resource = DocumentResource("/inbox/done/Doc.pdf", {
        "document": mock_doc,
        "paperless_client": mock_client,
        "share": mock_share,
        "tag_cache": {"processed": 2},
        "in_done_folder": True,
    })

    # Simulate MOVE to /inbox/Doc.pdf
    resource.move("/inbox/Doc.pdf")

    mock_client.remove_tag_from_document.assert_called_once_with(42, 2)
```

**Step 5: Commit**

```bash
git commit -m "feat: MOVE from done folder removes done_tag (bidirectional)"
```

---

### Task 2.5: MOVE Validation

Only allow moves between root ↔ done folder within same share. Reject all other moves.

**Files:**
- Modify: `src/paperless_webdav/webdav_provider.py`
- Modify: `tests/test_webdav_provider.py`

**Step 1: Write the failing tests**

```python
def test_move_rejects_cross_share_moves():
    """MOVE between different shares should be rejected."""
    resource = DocumentResource("/share1/doc.pdf", {...})

    with pytest.raises(DAVError) as exc:
        resource.move("/share2/doc.pdf")

    assert exc.value.status == 403


def test_move_rejects_invalid_destinations():
    """MOVE to invalid paths should be rejected."""
    resource = DocumentResource("/inbox/doc.pdf", {...})

    with pytest.raises(DAVError) as exc:
        resource.move("/inbox/subdir/doc.pdf")  # No subdirs allowed

    assert exc.value.status == 403
```

**Step 5: Commit**

```bash
git commit -m "feat: validate MOVE operations for done folder workflow"
```

---

## Phase 3: OIDC Authentication (Authentik)

### Task 3.1: Add OIDC Routes for Login Flow

**Files:**
- Create: `src/paperless_webdav/auth/oidc.py`
- Create: `tests/test_auth_oidc.py`

**Step 1: Write the failing test**

```python
# tests/test_auth_oidc.py
"""Tests for OIDC authentication flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from paperless_webdav.app import create_app


@pytest.fixture
def mock_oidc_settings(mock_settings):
    """Settings with OIDC mode enabled."""
    with patch.dict("os.environ", {
        "AUTH_MODE": "oidc",
        "OIDC_ISSUER": "https://auth.example.com",
        "OIDC_CLIENT_ID": "paperless-webdav",
        "OIDC_CLIENT_SECRET": "secret123",
    }):
        yield


@pytest.mark.asyncio
async def test_oidc_login_redirects_to_provider(mock_oidc_settings):
    """GET /ui/login in OIDC mode should redirect to OIDC provider."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ui/login", follow_redirects=False)

    assert response.status_code == 302
    assert "auth.example.com" in response.headers["location"]


@pytest.mark.asyncio
async def test_oidc_callback_creates_session(mock_oidc_settings):
    """OIDC callback should create session with user info."""
    app = create_app()

    with patch("paperless_webdav.auth.oidc.exchange_code_for_token") as mock_exchange:
        mock_exchange.return_value = {"sub": "user123", "preferred_username": "barry"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/auth/callback?code=abc123", follow_redirects=False)

    # Should redirect to token setup (no Paperless token yet)
    assert response.status_code == 302
    assert "/ui/token-setup" in response.headers["location"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_oidc.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/paperless_webdav/auth/oidc.py
"""OIDC authentication flow for Authentik."""

from typing import Annotated
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from paperless_webdav.config import Settings, get_settings
from paperless_webdav.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["oidc"])

# OAuth client configured lazily
_oauth: OAuth | None = None


def get_oauth(settings: Settings) -> OAuth:
    """Get or create OAuth client."""
    global _oauth
    if _oauth is None:
        _oauth = OAuth()
        _oauth.register(
            name="authentik",
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret.get_secret_value() if settings.oidc_client_secret else None,
            server_metadata_url=f"{settings.oidc_issuer}/.well-known/openid-configuration",
            client_kwargs={"scope": "openid profile email"},
        )
    return _oauth


@router.get("/auth/login")
async def oidc_login(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Initiate OIDC login flow - redirect to Authentik."""
    if settings.auth_mode != "oidc":
        return RedirectResponse(url="/ui/login")

    oauth = get_oauth(settings)
    redirect_uri = str(request.url_for("oidc_callback"))

    return await oauth.authentik.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def oidc_callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Handle OIDC callback from Authentik."""
    oauth = get_oauth(settings)

    try:
        token = await oauth.authentik.authorize_access_token(request)
    except Exception as e:
        logger.error("oidc_callback_error", error=str(e))
        return RedirectResponse(url="/ui/login?error=auth_failed")

    userinfo = token.get("userinfo", {})
    username = userinfo.get("preferred_username") or userinfo.get("sub")

    if not username:
        logger.error("oidc_no_username", userinfo=userinfo)
        return RedirectResponse(url="/ui/login?error=no_username")

    # Create partial session (no Paperless token yet)
    from paperless_webdav.auth.paperless import _create_session
    session_value = _create_session(username, "", settings)  # Empty token

    response = RedirectResponse(url="/ui/token-setup")
    response.set_cookie(
        key="session",
        value=session_value,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_expiry_hours * 3600,
    )

    logger.info("oidc_login_success", username=username)
    return response
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth_oidc.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/paperless_webdav/auth/oidc.py tests/test_auth_oidc.py
git commit -m "feat: add OIDC login flow for Authentik"
```

---

### Task 3.2: Token Setup Page for OIDC Users

After OIDC login, users need to enter their Paperless API token.

**Files:**
- Create: `src/paperless_webdav/ui/templates/token_setup.html`
- Modify: `src/paperless_webdav/ui/routes.py`
- Modify: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

Add to `tests/test_ui_routes.py`:

```python
@pytest.mark.asyncio
async def test_token_setup_page_renders(app_with_oidc_session):
    """Token setup page should render for OIDC users without token."""
    async with AsyncClient(transport=ASGITransport(app=app_with_oidc_session), base_url="http://test") as client:
        response = await client.get("/ui/token-setup")

    assert response.status_code == 200
    assert "Paperless API Token" in response.text


@pytest.mark.asyncio
async def test_token_setup_validates_and_stores_token(app_with_oidc_session):
    """Token setup should validate token against Paperless and store it."""
    with patch("paperless_webdav.ui.routes.PaperlessClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.validate_token = AsyncMock(return_value=True)
        mock_client.return_value = mock_instance

        async with AsyncClient(transport=ASGITransport(app=app_with_oidc_session), base_url="http://test") as client:
            response = await client.post("/ui/token-setup", data={"token": "valid-token"})

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/shares"
```

**Step 2-4: Standard TDD cycle**

**Step 5: Commit**

```bash
git add src/paperless_webdav/ui/templates/token_setup.html src/paperless_webdav/ui/routes.py tests/test_ui_routes.py
git commit -m "feat: add token setup page for OIDC users"
```

---

### Task 3.3: Store Encrypted Paperless Token in Database

**Files:**
- Modify: `src/paperless_webdav/services/shares.py` (add token storage)
- Modify: `tests/test_services_shares.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_store_user_token_encrypts_token(mock_session):
    """store_user_token should encrypt the token before storing."""
    from paperless_webdav.services.shares import store_user_token

    with patch("paperless_webdav.services.shares.TokenEncryption") as mock_enc:
        mock_enc_instance = MagicMock()
        mock_enc_instance.encrypt.return_value = b"encrypted"
        mock_enc.return_value = mock_enc_instance

        await store_user_token(mock_session, "barry", "plain-token", "base64key")

        mock_enc_instance.encrypt.assert_called_once_with("plain-token")


@pytest.mark.asyncio
async def test_get_user_token_decrypts_token(mock_session):
    """get_user_token should decrypt the stored token."""
    from paperless_webdav.services.shares import get_user_token

    # Setup: user with encrypted token
    mock_user = MagicMock()
    mock_user.paperless_token_encrypted = b"encrypted"
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user)))

    with patch("paperless_webdav.services.shares.TokenEncryption") as mock_enc:
        mock_enc_instance = MagicMock()
        mock_enc_instance.decrypt.return_value = "plain-token"
        mock_enc.return_value = mock_enc_instance

        token = await get_user_token(mock_session, "barry", "base64key")

        assert token == "plain-token"
```

**Step 5: Commit**

```bash
git commit -m "feat: store encrypted Paperless tokens in database"
```

---

### Task 3.4: Update UI Login to Support Both Modes

**Files:**
- Modify: `src/paperless_webdav/ui/templates/login.html`
- Modify: `src/paperless_webdav/ui/routes.py`
- Modify: `tests/test_ui_routes.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_login_page_shows_sso_button_in_oidc_mode(mock_oidc_settings):
    """Login page should show SSO button when auth_mode=oidc."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ui/login")

    assert "Login with SSO" in response.text
    # Should NOT show username/password form
    assert 'name="password"' not in response.text


@pytest.mark.asyncio
async def test_login_page_shows_form_in_paperless_mode(mock_settings):
    """Login page should show form when auth_mode=paperless."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ui/login")

    # Should show username/password form
    assert 'name="password"' in response.text
    # Should NOT show SSO button
    assert "Login with SSO" not in response.text
```

**Step 5: Commit**

```bash
git commit -m "feat: update login page to support both auth modes"
```

---

### Task 3.5: Load Token from Database for WebDAV and UI

When an OIDC user accesses WebDAV or UI, load their stored Paperless token.

**Files:**
- Modify: `src/paperless_webdav/auth/paperless.py`
- Modify: `src/paperless_webdav/webdav_auth.py`
- Modify tests

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_get_current_user_loads_token_from_db_if_missing(mock_oidc_settings):
    """get_current_user should load token from DB for OIDC users."""
    # Session has username but empty token (OIDC user)
    session_with_empty_token = create_session("barry", "")

    with patch("paperless_webdav.auth.paperless.get_user_token") as mock_get:
        mock_get.return_value = "db-stored-token"

        user = await get_current_user(session=session_with_empty_token, settings=mock_settings)

        assert user.token == "db-stored-token"
```

**Step 5: Commit**

```bash
git commit -m "feat: load Paperless token from database for OIDC users"
```

---

### Task 3.6: Add OIDC Router to App

**Files:**
- Modify: `src/paperless_webdav/app.py`
- Modify: `src/paperless_webdav/auth/__init__.py`

**Step 1: Update app.py**

Add conditional include of OIDC router when auth_mode=oidc.

**Step 5: Commit**

```bash
git commit -m "feat: conditionally include OIDC router based on auth_mode"
```

---

## Phase 4: Integration Testing

### Task 4.1: End-to-End Test for WebDAV Document Access

**Files:**
- Create: `tests/test_e2e_webdav.py`

Full test that:
1. Creates a share via API
2. Mounts WebDAV with test credentials
3. Lists documents
4. Downloads a document
5. Moves document to done folder
6. Verifies tag was added

**Step 5: Commit**

```bash
git commit -m "test: add end-to-end WebDAV document access test"
```

---

### Task 4.2: End-to-End Test for OIDC Flow

**Files:**
- Create: `tests/test_e2e_oidc.py`

Full test that:
1. Simulates OIDC redirect and callback
2. Submits Paperless token
3. Verifies token is stored encrypted
4. Accesses shares using stored token

**Step 5: Commit**

```bash
git commit -m "test: add end-to-end OIDC authentication test"
```

---

## Summary

**Total Tasks:** 16

**Phase 1 (WebDAV Integration):** 5 tasks
- Async bridge
- Wire provider to Paperless
- WebDAV Basic Auth
- Cheroot server
- Main entrypoint

**Phase 2 (Done Folder):** 5 tasks
- Filter root listing
- Show done folder contents
- MOVE root → done (add tag)
- MOVE done → root (remove tag)
- MOVE validation

**Phase 3 (OIDC):** 6 tasks
- OIDC routes
- Token setup page
- Encrypted token storage
- Dual-mode login page
- Token loading
- Router integration

**Phase 4 (Integration):** 2 tasks
- E2E WebDAV test
- E2E OIDC test

---

## Running the Project After Completion

```bash
cd /home/barry/paperless-webdav/.worktrees/dev
source .venv/bin/activate

# Set environment variables
export PAPERLESS_URL=https://paperless.example.com
export DATABASE_URL=postgresql://user:pass@localhost/paperless_webdav
export ENCRYPTION_KEY=$(python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())")
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# For OIDC mode:
export AUTH_MODE=oidc
export OIDC_ISSUER=https://auth.example.com/application/o/paperless-webdav
export OIDC_CLIENT_ID=paperless-webdav
export OIDC_CLIENT_SECRET=your-client-secret

# Run migrations
alembic upgrade head

# Start both servers
python -m paperless_webdav.main
# Admin UI: http://localhost:8080
# WebDAV: http://localhost:8081
```
