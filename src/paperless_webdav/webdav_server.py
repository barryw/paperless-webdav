# src/paperless_webdav/webdav_server.py
"""WebDAV server using wsgidav and cheroot."""

from collections.abc import Callable as ABCCallable, Iterable
from enum import Enum
from typing import Any, Callable

import cheroot.wsgi
from wsgidav.lock_man.lock_storage_redis import LockStorageRedis
from wsgidav.wsgidav_app import WsgiDAVApp

from paperless_webdav.webdav_auth import PaperlessBasicAuthenticator
from paperless_webdav.webdav_provider import PaperlessProvider
from paperless_webdav.logging import get_logger

logger = get_logger(__name__)


class WebDAVClient(Enum):
    """Known WebDAV client types with their quirks."""

    WINDOWS = "windows"  # Microsoft WebDAV MiniRedir - needs caching, has many quirks
    MACOS = "macos"  # macOS Finder/WebDAVFS - aggressive caching, needs no-cache headers
    LINUX = "linux"  # Linux clients (gvfs, davfs2) - generally well-behaved
    CYBERDUCK = "cyberduck"  # Cyberduck - well-behaved, cross-platform
    RCLONE = "rclone"  # rclone - well-behaved
    UNKNOWN = "unknown"  # Unknown client


def detect_webdav_client(user_agent: str) -> WebDAVClient:
    """Detect the WebDAV client type from User-Agent header.

    Args:
        user_agent: The HTTP User-Agent header value

    Returns:
        The detected WebDAVClient type
    """
    if not user_agent:
        return WebDAVClient.UNKNOWN

    ua_lower = user_agent.lower()

    # Check specific/well-behaved clients FIRST (before generic OS detection)
    # These clients may include OS info in their UA but have their own quirks

    # Cyberduck - well-behaved, cross-platform
    # Example: "Cyberduck/8.7.0.40629 (Mac OS X/14.0)"
    if "cyberduck" in ua_lower:
        return WebDAVClient.CYBERDUCK

    # rclone - well-behaved
    # Example: "rclone/v1.65.0"
    if "rclone" in ua_lower:
        return WebDAVClient.RCLONE

    # Linux clients - generally well-behaved
    # gvfs: "gvfs/1.50.0"
    # davfs2: "davfs2/1.6.1" (note: must check for "davfs2" not just "davfs" to avoid matching "WebDAVFS")
    if "gvfs" in ua_lower or "davfs2" in ua_lower:
        return WebDAVClient.LINUX

    # Now check OS-specific built-in clients (more quirky)

    # Windows WebDAV MiniRedir - many quirks
    # Example: "Microsoft-WebDAV-MiniRedir/10.0.26200"
    if "microsoft-webdav" in ua_lower or "miniredir" in ua_lower:
        return WebDAVClient.WINDOWS

    # macOS Finder / WebDAVFS - aggressive caching issues
    # Example: "WebDAVFS/3.0.0 (03008000) Darwin/23.0.0"
    if "webdavfs" in ua_lower or "darwin" in ua_lower:
        return WebDAVClient.MACOS

    # Also catch other macOS indicators
    if "macos" in ua_lower or "mac os" in ua_lower:
        return WebDAVClient.MACOS

    return WebDAVClient.UNKNOWN


class ClientCompatibilityMiddleware:
    """WSGI middleware that applies client-specific quirks and workarounds.

    Different WebDAV clients have different bugs and expectations. This middleware
    detects the client type and applies appropriate workarounds:

    Windows (MiniRedir):
        - Needs caching to work reliably (files must fully download before apps open them)
        - Has issues with non-standard ports, basic auth over HTTP, file size limits
        - Many quirks documented at https://sabre.io/dav/clients/windows/

    macOS (Finder/WebDAVFS):
        - Caches responses aggressively, causing stale/truncated files
        - Needs Cache-Control: no-store headers
        - Creates .DS_Store and ._* resource fork files
        - Uses chunked transfer encoding for uploads

    Linux (gvfs, davfs2):
        - Generally well-behaved, follows specs more closely

    The middleware also:
        - Logs client type for debugging
        - Stores client info in environ["webdav.client"] for downstream use
    """

    def __init__(self, app: ABCCallable[..., Iterable[bytes]]) -> None:
        self._app = app

    def __call__(
        self,
        environ: dict[str, Any],
        start_response: ABCCallable[..., Any],
    ) -> Iterable[bytes]:
        user_agent = environ.get("HTTP_USER_AGENT", "")
        client = detect_webdav_client(user_agent)

        # Store client info for downstream use (e.g., in provider)
        environ["webdav.client"] = client
        environ["webdav.client_name"] = client.value

        # Log client type on first request (OPTIONS is typically first)
        method = environ.get("REQUEST_METHOD", "")
        if method == "OPTIONS":
            logger.debug(
                "webdav_client_detected",
                client=client.value,
                user_agent=user_agent[:100],  # Truncate long UAs
            )

        def custom_start_response(
            status: str,
            response_headers: list[tuple[str, str]],
            exc_info: Any = None,
        ) -> Any:
            # Apply client-specific header modifications
            self._apply_client_headers(client, response_headers)
            return start_response(status, response_headers, exc_info)

        return self._app(environ, custom_start_response)

    def _apply_client_headers(
        self,
        client: WebDAVClient,
        headers: list[tuple[str, str]],
    ) -> None:
        """Apply client-specific response headers.

        Args:
            client: The detected client type
            headers: Response headers list to modify in-place
        """
        if client == WebDAVClient.MACOS:
            # macOS Finder caches aggressively - disable caching to prevent
            # stale or truncated files
            headers.append(("Cache-Control", "no-store, no-cache, must-revalidate"))
            headers.append(("Pragma", "no-cache"))

        # Windows MiniRedir: Let it cache (default behavior)
        # wsgidav already sends MS-Author-Via: DAV header

        # For all clients: Ensure Content-Type has a default
        # (some clients behave badly without it)
        # This is handled by wsgidav, but we could add fallbacks here if needed


# Keep old name as alias for backwards compatibility with tests
NoCacheMiddleware = ClientCompatibilityMiddleware


def _is_macos_client(user_agent: str) -> bool:
    """Check if the User-Agent indicates a macOS WebDAV client.

    Deprecated: Use detect_webdav_client() instead.

    Args:
        user_agent: The HTTP User-Agent header value

    Returns:
        True if this appears to be a macOS client (Finder/WebDAVFS)
    """
    return detect_webdav_client(user_agent) == WebDAVClient.MACOS


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
    redis_host: str | None = None,
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: str | None = None,
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
        redis_host: Redis host for distributed lock storage
        redis_port: Redis port (default 6379)
        redis_db: Redis database number (default 0)
        redis_password: Redis password (optional)

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
        # Client compatibility settings
        # MS-Author-Via header is enabled by default in wsgidav
        "add_header_MS_Author_Via": True,
        # Hotfixes for various client quirks
        "hotfixes": {
            # Handle Windows Win32LastModifiedTime property (helps Win10, not Win7)
            "emulate_win32_lastmod": True,
            # Re-encode PATH_INFO using UTF-8 for non-ASCII filenames
            "re_encode_path_info": True,
            # Don't force unquote (let WSGI framework handle it)
            "unquote_path_info": False,
            # Accept 'OPTIONS /' as 'OPTIONS *' for WinXP/Vista compatibility
            "treat_root_options_as_asterisk": True,
        },
        # Store references for request handlers
        "paperless_url": paperless_url,
        "share_loader": share_loader,
    }

    # Configure distributed lock storage if Redis is available
    if redis_host:
        lock_storage = LockStorageRedis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
        )
        config["lock_storage"] = lock_storage
        logger.info(
            "redis_lock_storage_configured",
            host=redis_host,
            port=redis_port,
            db=redis_db,
        )

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
        redis_host: str | None = None,
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: str | None = None,
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
            redis_host: Redis host for distributed lock storage
            redis_port: Redis port (default 6379)
            redis_db: Redis database number (default 0)
            redis_password: Redis password (optional)
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
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            redis_password=redis_password,
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
