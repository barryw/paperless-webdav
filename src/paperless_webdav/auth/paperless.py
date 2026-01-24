# src/paperless_webdav/auth/paperless.py
"""Paperless-native authentication via /api/token/ endpoint."""

from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from paperless_webdav.config import get_settings, Settings
from paperless_webdav.database import get_session
from paperless_webdav.logging import get_logger
from paperless_webdav.services.shares import get_user_token

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Request body for login endpoint."""

    username: str
    password: str


class UserResponse(BaseModel):
    """Response body containing user information."""

    username: str


@dataclass
class AuthenticatedUser:
    """Authenticated user with Paperless token."""

    username: str
    token: str


async def _authenticate_with_paperless(
    username: str, password: str, paperless_url: str
) -> tuple[str, None] | tuple[None, str]:
    """Authenticate with Paperless and return (token, None) or (None, error_message).

    Makes a request to the Paperless /api/token/ endpoint to validate
    credentials and obtain an API token.

    Args:
        username: The username to authenticate with.
        password: The password to authenticate with.
        paperless_url: The base URL of the Paperless server.

    Returns:
        A tuple of (token, None) on success, or (None, error_message) on failure.
    """
    token_url = f"{paperless_url.rstrip('/')}/api/token/"

    try:
        async with httpx.AsyncClient() as client:
            paperless_response = await client.post(
                token_url,
                json={"username": username, "password": password},
            )
    except httpx.RequestError as e:
        logger.error("paperless_connection_error", error=str(e))
        return None, "Failed to connect to Paperless server"

    if paperless_response.status_code == 400:
        logger.info("login_failed", username=username)
        return None, "Invalid credentials"

    if paperless_response.status_code >= 500:
        logger.error("paperless_server_error", status=paperless_response.status_code)
        return None, "Paperless server error"

    if paperless_response.status_code != 200:
        logger.error("paperless_unexpected_status", status=paperless_response.status_code)
        return None, "Unexpected response from Paperless server"

    # Extract token from response
    try:
        token_data = paperless_response.json()
        token = token_data["token"]
    except (KeyError, ValueError) as e:
        logger.error("paperless_invalid_response", error=str(e))
        return None, "Invalid response from Paperless server"

    return token, None


def _get_serializer(settings: Settings) -> URLSafeTimedSerializer:
    """Get the session serializer."""
    return URLSafeTimedSerializer(settings.secret_key.get_secret_value())


def _create_session(username: str, token: str, settings: Settings) -> str:
    """Create an encrypted session cookie value."""
    serializer = _get_serializer(settings)
    return serializer.dumps({"username": username, "token": token})


def _validate_session(session_value: str, settings: Settings) -> AuthenticatedUser | None:
    """Validate and decode a session cookie value.

    Returns the AuthenticatedUser if valid, None otherwise.
    """
    if not session_value:
        return None

    serializer = _get_serializer(settings)
    try:
        # Session expiry in seconds (hours * 3600)
        max_age = settings.session_expiry_hours * 3600
        data = serializer.loads(session_value, max_age=max_age)
        return AuthenticatedUser(username=data["username"], token=data["token"])
    except SignatureExpired:
        logger.debug("session_expired")
        return None
    except BadSignature:
        logger.debug("session_invalid_signature")
        return None
    except (KeyError, TypeError):
        logger.debug("session_invalid_data")
        return None


async def _load_token_from_db(username: str, settings: Settings) -> str | None:
    """Load user's Paperless token from database.

    Args:
        username: The username to look up.
        settings: Application settings.

    Returns:
        The decrypted token, or None if not found.
    """
    try:
        async for db_session in get_session():
            token = await get_user_token(
                db_session,
                username,
                settings.encryption_key.get_secret_value(),
            )
            return token
    except RuntimeError:
        # Database not initialized yet
        logger.debug("database_not_available_for_token_lookup")
        return None


async def get_current_user(
    session: Annotated[str | None, Cookie()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> AuthenticatedUser:
    """Get the current authenticated user from session.

    For OIDC users (session with username but empty token), loads the
    Paperless token from the database.

    Raises HTTPException 401 if not authenticated.
    """
    if settings is None:
        settings = get_settings()

    user = _validate_session(session or "", settings)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # If session has username but empty token (OIDC user), load token from DB
    if user.username and not user.token:
        db_token = await _load_token_from_db(user.username, settings)
        if db_token:
            logger.debug("loaded_token_from_db", username=user.username)
            return AuthenticatedUser(username=user.username, token=db_token)
        else:
            # User has no token stored - they need to set up their token
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

    return user


async def get_current_user_optional(
    session: Annotated[str | None, Cookie()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> AuthenticatedUser | None:
    """Get the current user if authenticated, None otherwise.

    For OIDC users (session with username but empty token), loads the
    Paperless token from the database.
    """
    if settings is None:
        settings = get_settings()

    user = _validate_session(session or "", settings)
    if user is None:
        return None

    # If session has username but empty token (OIDC user), load token from DB
    if user.username and not user.token:
        db_token = await _load_token_from_db(user.username, settings)
        if db_token:
            logger.debug("loaded_token_from_db", username=user.username)
            return AuthenticatedUser(username=user.username, token=db_token)
        else:
            # No token in session or DB - not fully authenticated
            return None

    return user


@router.post("/login", response_model=UserResponse)
async def login(
    credentials: LoginRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    """Login with Paperless credentials.

    Calls the Paperless /api/token/ endpoint to validate credentials
    and obtain an API token. On success, creates a session cookie.
    """
    token, error = await _authenticate_with_paperless(
        credentials.username, credentials.password, settings.paperless_url
    )

    if error is not None:
        # Map error messages to appropriate HTTP status codes
        if error == "Invalid credentials":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error,
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error,
        )

    # Create session cookie
    session_value = _create_session(credentials.username, token, settings)
    response.set_cookie(
        key="session",
        value=session_value,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_expiry_hours * 3600,
    )

    logger.info("login_success", username=credentials.username)
    return UserResponse(username=credentials.username)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """Logout and clear the session cookie."""
    response.set_cookie(
        key="session",
        value="",
        httponly=True,
        samesite="lax",
        max_age=0,
    )
    logger.info("logout_success")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> UserResponse:
    """Get current user information."""
    return UserResponse(username=current_user.username)
