# src/paperless_webdav/webdav_auth.py
"""HTTP Basic authentication for WebDAV using Paperless or LDAP credentials."""

import hashlib
import time
from typing import Any

import ldap  # type: ignore[import-untyped]

# Auth cache: maps (username, password_hash) -> (token, expiry_time)
_auth_cache: dict[tuple[str, str], tuple[str, float]] = {}
AUTH_CACHE_TTL = 300  # 5 minutes
from wsgidav.dc.base_dc import BaseDomainController  # type: ignore[import-untyped]

from paperless_webdav.async_bridge import run_async
from paperless_webdav.auth.paperless import _authenticate_with_paperless
from paperless_webdav.logging import get_logger
from paperless_webdav.database import get_sync_session
from paperless_webdav.models import User
from paperless_webdav.encryption import TokenEncryption

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
        ldap_url: str | None = None,
        ldap_base_dn: str | None = None,
        ldap_bind_dn: str | None = None,
        ldap_bind_password: str | None = None,
    ) -> None:
        """Initialize the authenticator.

        Args:
            paperless_url: Base URL of the Paperless server.
            auth_mode: Authentication mode ("paperless" or "oidc").
            encryption_key: Base64-encoded encryption key for token decryption (required for OIDC).
            ldap_url: LDAP server URL (e.g., ldap://server:389).
            ldap_base_dn: Base DN for LDAP user lookups.
            ldap_bind_dn: Service account DN for LDAP bind (e.g., cn=akadmin,ou=users,dc=ldap,dc=goauthentik,dc=io).
            ldap_bind_password: Service account password for LDAP bind.
        """
        # Pass None for wsgidav_app and config - we don't need them
        super().__init__(None, None)
        self._paperless_url = paperless_url
        self._auth_mode = auth_mode
        self._encryption_key = encryption_key
        self._ldap_url = ldap_url
        self._ldap_base_dn = ldap_base_dn
        self._ldap_bind_dn = ldap_bind_dn
        self._ldap_bind_password = ldap_bind_password
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

    def _authenticate_ldap(self, username: str, password: str) -> bool:
        """Authenticate user against LDAP server.

        Uses service account bind if configured, otherwise direct bind.

        Args:
            username: Username to authenticate.
            password: Password to authenticate.

        Returns:
            True if authentication succeeded, False otherwise.
        """
        if not self._ldap_url or not self._ldap_base_dn:
            logger.warning("ldap_not_configured")
            return False

        try:
            conn = ldap.initialize(self._ldap_url)
            conn.set_option(ldap.OPT_REFERRALS, 0)
            conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 10)

            # If service account configured, use search-then-bind pattern
            if self._ldap_bind_dn and self._ldap_bind_password:
                # First bind as service account
                conn.simple_bind_s(self._ldap_bind_dn, self._ldap_bind_password)
                logger.debug("ldap_service_bind_success")

                # Search for the user
                search_base = self._ldap_base_dn
                search_filter = f"(cn={username})"
                result = conn.search_s(search_base, ldap.SCOPE_SUBTREE, search_filter)

                if not result:
                    logger.info("ldap_user_not_found", username=username)
                    conn.unbind_s()
                    return False

                user_dn = result[0][0]
                logger.debug("ldap_user_found", user_dn=user_dn)

                # Rebind as the user to verify password
                conn.simple_bind_s(user_dn, password)
                conn.unbind_s()
                logger.info("ldap_auth_success", username=username)
                return True
            else:
                # Direct bind - construct user DN
                user_dn = f"cn={username},ou=users,{self._ldap_base_dn}"
                conn.simple_bind_s(user_dn, password)
                conn.unbind_s()
                logger.info("ldap_auth_success", username=username)
                return True

        except ldap.INVALID_CREDENTIALS:
            logger.info("ldap_auth_failed_invalid_credentials", username=username)
            return False
        except ldap.SERVER_DOWN:
            logger.error("ldap_server_down", url=self._ldap_url)
            return False
        except ldap.LDAPError as e:
            logger.error("ldap_auth_error", username=username, error=str(e))
            return False

    def _load_token_from_db(self, username: str) -> str | None:
        """Load user's Paperless token from database.

        Uses synchronous database access since WebDAV runs in a separate thread.

        Args:
            username: The username to look up.

        Returns:
            The decrypted token, or None if not found or DB unavailable.
        """
        if not self._encryption_key:
            logger.debug("no_encryption_key_for_token_lookup")
            return None

        try:
            with get_sync_session() as session:
                from sqlalchemy import select
                stmt = select(User).where(User.external_id == username)
                result = session.execute(stmt)
                user = result.scalar_one_or_none()

                if user is None:
                    logger.debug("user_not_found_in_db", username=username)
                    return None

                if user.paperless_token_encrypted is None:
                    logger.debug("user_has_no_token", username=username)
                    return None

                # Decrypt and return the token
                encryption = TokenEncryption(self._encryption_key)
                token = encryption.decrypt(user.paperless_token_encrypted)
                logger.debug("token_loaded_from_db", username=username)
                return token
        except RuntimeError as e:
            logger.debug("database_not_available_for_webdav_token_lookup", error=str(e))
            return None
        except Exception as e:
            logger.error("token_lookup_error", username=username, error=str(e))
            return None

    def basic_auth_user(
        self, realm: str, username: str, password: str, environ: dict[str, Any]
    ) -> bool | str:
        """Authenticate user with Basic auth credentials.

        In OIDC mode, authenticates against LDAP (Authentik), then loads
        the user's Paperless API token from the database.

        In paperless mode, validates credentials against the Paperless
        /api/token/ endpoint.

        On success, stores the returned token for later use by the
        WebDAV provider. Results are cached for 5 minutes to avoid
        repeated LDAP/API calls.

        Args:
            realm: Authentication realm.
            username: Username from Basic auth header.
            password: Password from Basic auth header.
            environ: WSGI environ dict.

        Returns:
            Username string if authenticated, False otherwise.
        """
        # Check cache first
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cache_key = (username, password_hash)
        now = time.time()

        if cache_key in _auth_cache:
            cached_token, expiry = _auth_cache[cache_key]
            if now < expiry:
                # Cache hit - use cached token
                self._user_tokens[username] = cached_token
                environ["paperless.username"] = username
                environ["paperless.token"] = cached_token
                logger.debug("webdav_auth_cache_hit", username=username)
                return username
            else:
                # Cache expired
                del _auth_cache[cache_key]

        token = None

        # In OIDC mode, try LDAP first, fall back to token-based auth
        if self._auth_mode == "oidc":
            db_token = self._load_token_from_db(username)

            # Try LDAP authentication if configured
            if self._ldap_url and self._ldap_base_dn:
                if self._authenticate_ldap(username, password):
                    if db_token:
                        token = db_token
                        logger.info("webdav_auth_success_ldap", username=username)
                    else:
                        logger.info("webdav_auth_failed_no_token", username=username)
                        return False
                else:
                    # LDAP failed, try token-based auth as fallback
                    if db_token and password == db_token:
                        token = db_token
                        logger.info("webdav_auth_success_token", username=username)
                    else:
                        logger.info("webdav_auth_failed", username=username)
                        return False
            else:
                # No LDAP configured, use token-based auth
                if db_token and password == db_token:
                    token = db_token
                    logger.info("webdav_auth_success_token", username=username)
                else:
                    logger.info("webdav_auth_failed_token_mismatch", username=username)
                    return False

        # In paperless mode, authenticate against Paperless API
        if token is None:
            auth_token, error = run_async(
                _authenticate_with_paperless(username, password, self._paperless_url)
            )

            if error is not None or auth_token is None:
                logger.info("webdav_auth_failed", username=username, error=error)
                return False

            token = auth_token
            logger.info("webdav_auth_success", username=username)

        # Cache the successful authentication
        _auth_cache[cache_key] = (token, now + AUTH_CACHE_TTL)

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
