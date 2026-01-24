# src/paperless_webdav/webdav_auth.py
"""HTTP Basic authentication for WebDAV using Paperless credentials."""

from typing import Any

from wsgidav.dc.base_dc import BaseDomainController  # type: ignore[import-untyped]

from paperless_webdav.async_bridge import run_async
from paperless_webdav.auth.paperless import _authenticate_with_paperless
from paperless_webdav.logging import get_logger
from paperless_webdav.services.shares import get_user_token
from paperless_webdav.database import get_session

logger = get_logger(__name__)


class PaperlessBasicAuthenticator(BaseDomainController):  # type: ignore[misc]
    """wsgidav domain controller that authenticates against Paperless.

    Validates HTTP Basic Auth credentials by calling the Paperless
    /api/token/ endpoint. Stores the returned token for use by
    the WebDAV provider when fetching documents.

    In OIDC mode, also attempts to load the user's stored token from
    the database.
    """

    def __init__(
        self,
        paperless_url: str,
        auth_mode: str = "paperless",
        encryption_key: str | None = None,
    ) -> None:
        """Initialize the authenticator.

        Args:
            paperless_url: Base URL of the Paperless server.
            auth_mode: Authentication mode ("paperless" or "oidc").
            encryption_key: Base64-encoded encryption key for token decryption (required for OIDC).
        """
        # Pass None for wsgidav_app and config - we don't need them
        super().__init__(None, None)
        self._paperless_url = paperless_url
        self._auth_mode = auth_mode
        self._encryption_key = encryption_key
        self._user_tokens: dict[str, str] = {}

    def get_domain_realm(self, path_info: str, environ: dict[str, Any] | None) -> str:
        """Return the authentication realm.

        Args:
            path_info: The URL path being accessed.
            environ: WSGI environ dict, or None during startup checks.

        Returns:
            The realm string for authentication prompts.
        """
        return "Paperless WebDAV"

    def require_authentication(self, realm: str, environ: dict[str, Any] | None) -> bool:
        """Always require authentication for WebDAV.

        Args:
            realm: Authentication realm.
            environ: WSGI environ dict, or None during startup checks.

        Returns:
            True to require authentication.
        """
        return True

    def supports_http_digest_auth(self) -> bool:
        """We only support Basic auth (need password to get token).

        Returns:
            False - digest auth is not supported.
        """
        return False

    def _load_token_from_db(self, username: str) -> str | None:
        """Load user's Paperless token from database.

        Args:
            username: The username to look up.

        Returns:
            The decrypted token, or None if not found or DB unavailable.
        """
        if not self._encryption_key:
            return None

        # Capture encryption_key to satisfy type checker
        encryption_key = self._encryption_key

        async def _fetch_token() -> str | None:
            try:
                async for db_session in get_session():
                    return await get_user_token(
                        db_session, username, encryption_key
                    )
                return None  # Generator yielded nothing
            except RuntimeError:
                # Database not initialized
                logger.debug("database_not_available_for_webdav_token_lookup")
                return None

        return run_async(_fetch_token())

    def basic_auth_user(
        self, realm: str, username: str, password: str, environ: dict[str, Any]
    ) -> bool | str:
        """Authenticate user with Basic auth credentials.

        In OIDC mode, first attempts to load the user's stored token from
        the database. If not found, falls back to Paperless authentication.

        In paperless mode, validates credentials against the Paperless
        /api/token/ endpoint.

        On success, stores the returned token for later use by the
        WebDAV provider.

        Args:
            realm: Authentication realm.
            username: Username from Basic auth header.
            password: Password from Basic auth header.
            environ: WSGI environ dict.

        Returns:
            Username string if authenticated, False otherwise.
        """
        token = None

        # In OIDC mode, try loading token from database first
        if self._auth_mode == "oidc":
            db_token = self._load_token_from_db(username)
            if db_token:
                token = db_token
                logger.info("webdav_auth_success_from_db", username=username)

        # Fall back to Paperless authentication if no DB token
        if token is None:
            auth_token, error = run_async(
                _authenticate_with_paperless(username, password, self._paperless_url)
            )

            if error is not None or auth_token is None:
                logger.info("webdav_auth_failed", username=username, error=error)
                return False

            token = auth_token
            logger.info("webdav_auth_success", username=username)

        # Store token for provider access
        self._user_tokens[username] = token
        environ["paperless.username"] = username
        environ["paperless.token"] = token

        return username

    def get_token(self, username: str) -> str | None:
        """Get stored token for a user.

        Args:
            username: The username to look up.

        Returns:
            The stored token, or None if not found.
        """
        return self._user_tokens.get(username)
