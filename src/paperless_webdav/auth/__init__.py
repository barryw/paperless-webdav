# src/paperless_webdav/auth/__init__.py
"""Authentication module for Paperless-WebDAV."""

from paperless_webdav.auth import oidc
from paperless_webdav.auth.oidc import router as oidc_router
from paperless_webdav.auth.paperless import (
    AuthenticatedUser,
    get_current_user,
    get_current_user_optional,
    router as auth_router,
)

__all__ = [
    "AuthenticatedUser",
    "get_current_user",
    "get_current_user_optional",
    "auth_router",
    "oidc",
    "oidc_router",
]
