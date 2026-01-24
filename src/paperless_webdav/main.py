# src/paperless_webdav/main.py
"""Main entrypoint for running both Admin UI and WebDAV servers."""

import signal
import sys
import threading
from typing import Any

import uvicorn
from sqlalchemy import select

from paperless_webdav.async_bridge import run_async
from paperless_webdav.config import get_settings
from paperless_webdav.database import _async_session_factory, close_database, init_database
from paperless_webdav.logging import get_logger, setup_logging
from paperless_webdav.models import Share
from paperless_webdav.webdav_server import WebDAVServer

logger = get_logger(__name__)


async def _load_all_shares() -> list[Share]:
    """Load all shares from database."""
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

    # Create WebDAV server with auth mode and encryption key for OIDC support
    webdav_server = WebDAVServer(
        host="0.0.0.0",
        port=settings.webdav_port,
        paperless_url=settings.paperless_url,
        share_loader=load_shares_sync,
        auth_mode=settings.auth_mode,
        encryption_key=settings.encryption_key.get_secret_value(),
    )

    # Run WebDAV server in background thread
    webdav_thread = threading.Thread(target=webdav_server.start, daemon=True)
    webdav_thread.start()
    logger.info("webdav_server_started", port=settings.webdav_port)

    # Handle shutdown signals
    def shutdown(signum: int, frame: Any) -> None:
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
