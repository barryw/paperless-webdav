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
    auth_mode: str = "paperless",
    encryption_key: str | None = None,
) -> WsgiDAVApp:
    """Create the wsgidav WSGI application.

    Args:
        paperless_url: Base URL of Paperless-ngx
        share_loader: Callable that returns dict of share configs
        auth_mode: Authentication mode ("paperless" or "oidc")
        encryption_key: Base64-encoded encryption key for OIDC token decryption

    Returns:
        Configured WsgiDAVApp instance
    """
    provider = PaperlessProvider(paperless_url=paperless_url)

    # Create authenticator with auth mode and encryption key
    authenticator = PaperlessBasicAuthenticator(
        paperless_url, auth_mode=auth_mode, encryption_key=encryption_key
    )

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
        auth_mode: str = "paperless",
        encryption_key: str | None = None,
    ) -> None:
        """Initialize the WebDAV server.

        Args:
            host: Host to bind to
            port: Port to bind to
            paperless_url: Base URL of Paperless-ngx
            share_loader: Callable that returns dict of share configs
            auth_mode: Authentication mode ("paperless" or "oidc")
            encryption_key: Base64-encoded encryption key for OIDC token decryption
        """
        self._app = create_webdav_app(
            paperless_url=paperless_url,
            share_loader=share_loader,
            auth_mode=auth_mode,
            encryption_key=encryption_key,
        )
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
