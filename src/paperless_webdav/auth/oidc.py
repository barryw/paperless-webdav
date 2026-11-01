# src/paperless_webdav/auth/oidc.py
"""OIDC authentication routes for Authentik SSO."""

import os
from typing import Annotated

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from paperless_webdav.config import Settings, get_settings
from paperless_webdav.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["oidc"])

_oauth: OAuth | None = None


def get_oauth(settings: Settings) -> OAuth:
    """Get or create the OAuth client instance.

    Creates the OAuth client on first call and caches it for subsequent calls.
    Registers the Authentik OIDC provider with the configured settings.

    Args:
        settings: Application settings containing OIDC configuration.

    Returns:
        Configured OAuth instance with Authentik provider registered.
    """
    global _oauth
    if _oauth is None:
        # Configure httpx client with CA bundle and timeout
        ssl_cert_file = os.environ.get("SSL_CERT_FILE")
        verify = ssl_cert_file if ssl_cert_file else True

        _oauth = OAuth()
        _oauth.register(
            name="authentik",
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret.get_secret_value()
            if settings.oidc_client_secret
            else None,
            server_metadata_url=f"{settings.oidc_issuer}/.well-known/openid-configuration",
            client_kwargs={
                "scope": "openid profile email",
                "timeout": httpx.Timeout(30.0),
                "verify": verify,
            },
        )
    return _oauth


@router.get("/auth/login")
async def oidc_login(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Initiate OIDC login flow by redirecting to Authentik.

    Only active when auth_mode="oidc". In Paperless auth mode,
    redirects to the standard UI login page instead.

    Args:
        request: The incoming request.
        settings: Application settings.

    Returns:
        RedirectResponse to either Authentik or /ui/login.
    """
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
    """Handle OIDC callback from Authentik after authentication.

    Exchanges the authorization code for tokens, extracts user information,
    and creates a session. Returning users with a stored Paperless token go
    directly to their shares; first-time users are sent to token setup.

    Args:
        request: The incoming request with authorization code.
        settings: Application settings.

    Returns:
        RedirectResponse to /ui/shares for returning users, /ui/token-setup for
        first-time users, or /ui/login on error.
    """
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

    from paperless_webdav.auth.paperless import _create_session, _load_token_from_db

    stored_token = await _load_token_from_db(username, settings)
    session_value = _create_session(username, "", settings)
    redirect_url = "/ui/shares" if stored_token else "/ui/token-setup"

    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key="session",
        value=session_value,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_expiry_hours * 3600,
        path="/",
    )
    logger.info("oidc_login_success", username=username)
    return response
