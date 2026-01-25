# src/paperless_webdav/webdav_server.py
"""WebDAV server using wsgidav and cheroot."""

from collections.abc import Callable as ABCCallable, Iterable
from typing import Any, Callable

import cheroot.wsgi
from wsgidav.wsgidav_app import WsgiDAVApp

from paperless_webdav.webdav_auth import PaperlessBasicAuthenticator
from paperless_webdav.webdav_provider import PaperlessProvider
from paperless_webdav.logging import get_logger

logger = get_logger(__name__)


class NoCacheMiddleware:
    """WSGI middleware that adds Cache-Control headers to prevent caching.

    macOS WebDAV client (Finder) caches responses aggressively, which can cause
    stale or truncated files to be served from cache. This middleware adds
    Cache-Control: no-store to all responses to prevent this.
    """

    def __init__(self, app: ABCCallable[..., Iterable[bytes]]) -> None:
        self._app = app

    def __call__(
        self,
        environ: dict[str, Any],
        start_response: ABCCallable[..., Any],
    ) -> Iterable[bytes]:
        def custom_start_response(
            status: str,
            response_headers: list[tuple[str, str]],
            exc_info: Any = None,
        ) -> Any:
            # Add cache control headers
            response_headers.append(("Cache-Control", "no-store, no-cache, must-revalidate"))
            response_headers.append(("Pragma", "no-cache"))
            return start_response(status, response_headers, exc_info)

        return self._app(environ, custom_start_response)


def _make_authenticator_class(
    paperless_url: str,
    auth_mode: str,
    encryption_key: str | None,
    ldap_url: str | None = None,
    ldap_base_dn: str | None = None,
    ldap_bind_dn: str | None = None,
    ldap_bind_password: str | None = None,
) -> type[PaperlessBasicAuthenticator]:
    """Create a configured authenticator class that wsgidav can instantiate.

    wsgidav's make_domain_controller uses inspect.isclass() and expects
    to instantiate the class with (wsgidav_app, config) args.
    """

    class ConfiguredAuthenticator(PaperlessBasicAuthenticator):
        def __init__(self, wsgidav_app: Any, config: dict[str, Any]) -> None:
            super().__init__(
                paperless_url,
                auth_mode=auth_mode,
                encryption_key=encryption_key,
                ldap_url=ldap_url,
                ldap_base_dn=ldap_base_dn,
                ldap_bind_dn=ldap_bind_dn,
                ldap_bind_password=ldap_bind_password,
            )

    return ConfiguredAuthenticator


def create_webdav_app(
    paperless_url: str,
    share_loader: Callable[[], dict[str, Any]],
    auth_mode: str = "paperless",
    encryption_key: str | None = None,
    ldap_url: str | None = None,
    ldap_base_dn: str | None = None,
    ldap_bind_dn: str | None = None,
    ldap_bind_password: str | None = None,
) -> WsgiDAVApp:
    """Create the wsgidav WSGI application.

    Args:
        paperless_url: Base URL of Paperless-ngx
        share_loader: Callable that returns dict of share configs
        auth_mode: Authentication mode ("paperless" or "oidc")
        encryption_key: Base64-encoded encryption key for OIDC token decryption
        ldap_url: LDAP server URL for OIDC mode authentication
        ldap_base_dn: LDAP base DN for user lookups
        ldap_bind_dn: Service account DN for LDAP bind
        ldap_bind_password: Service account password for LDAP bind

    Returns:
        Configured WsgiDAVApp instance
    """
    provider = PaperlessProvider(paperless_url=paperless_url, share_loader=share_loader)

    # Create authenticator class that captures our configuration
    AuthenticatorClass = _make_authenticator_class(
        paperless_url,
        auth_mode,
        encryption_key,
        ldap_url,
        ldap_base_dn,
        ldap_bind_dn,
        ldap_bind_password,
    )

    config = {
        "provider_mapping": {"/": provider},
        "http_authenticator": {
            "domain_controller": AuthenticatorClass,
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
        },
        "simple_dc": {"user_mapping": {}},  # Not used, but required
        "verbose": 5,
        "logging": {
            "enable": True,
            "enable_loggers": ["wsgidav"],
        },
        # Store references for request handlers
        "paperless_url": paperless_url,
        "share_loader": share_loader,
    }

    app = WsgiDAVApp(config)
    # Wrap with no-cache middleware to prevent macOS Finder caching issues
    return NoCacheMiddleware(app)


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
        ldap_url: str | None = None,
        ldap_base_dn: str | None = None,
        ldap_bind_dn: str | None = None,
        ldap_bind_password: str | None = None,
    ) -> None:
        """Initialize the WebDAV server.

        Args:
            host: Host to bind to
            port: Port to bind to
            paperless_url: Base URL of Paperless-ngx
            share_loader: Callable that returns dict of share configs
            auth_mode: Authentication mode ("paperless" or "oidc")
            encryption_key: Base64-encoded encryption key for OIDC token decryption
            ldap_url: LDAP server URL for OIDC mode authentication
            ldap_base_dn: LDAP base DN for user lookups
            ldap_bind_dn: Service account DN for LDAP bind
            ldap_bind_password: Service account password for LDAP bind
        """
        self._app = create_webdav_app(
            paperless_url=paperless_url,
            share_loader=share_loader,
            auth_mode=auth_mode,
            encryption_key=encryption_key,
            ldap_url=ldap_url,
            ldap_base_dn=ldap_base_dn,
            ldap_bind_dn=ldap_bind_dn,
            ldap_bind_password=ldap_bind_password,
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
