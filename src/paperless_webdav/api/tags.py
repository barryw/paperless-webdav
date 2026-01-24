# src/paperless_webdav/api/tags.py
"""Tags API endpoints - proxies tag operations to Paperless-ngx."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from paperless_webdav.config import get_settings
from paperless_webdav.logging import get_logger
from paperless_webdav.paperless_client import PaperlessClient, PaperlessTag
from paperless_webdav.schemas import TagResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tags", tags=["tags"])


# Placeholder types for auth
class User:
    """Placeholder user type."""

    id: UUID
    external_id: str


def _tags_to_response(tags: list[PaperlessTag]) -> list[TagResponse]:
    """Convert PaperlessTag objects to TagResponse schemas."""
    return [
        TagResponse(id=tag.id, name=tag.name, slug=tag.slug, color=tag.color)
        for tag in tags
    ]


# =============================================================================
# Placeholder functions (to be wired to real implementations in Task 2.4)
# =============================================================================


def get_current_user() -> User:
    """
    Placeholder authentication dependency.

    Will be replaced with real Paperless authentication in Task 2.4.
    """
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def get_paperless_client() -> PaperlessClient:
    """
    Get a PaperlessClient instance for the current request.

    Note: In a real implementation, we would get the user's token from
    the session/auth. For now, we use a placeholder token that will be
    replaced in Task 2.4 when authentication is wired up.
    """
    settings = get_settings()
    # Placeholder: real token will come from authenticated user's session
    return PaperlessClient(base_url=settings.paperless_url, token="placeholder")


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=list[TagResponse])
async def list_tags(
    current_user: Annotated[User, Depends(get_current_user)],
    client: Annotated[PaperlessClient, Depends(get_paperless_client)],
) -> list[TagResponse]:
    """
    List all tags from Paperless-ngx.

    Proxies the request to the Paperless API and returns all available tags.
    """
    tags = await client.get_tags()
    logger.debug("tags_listed", count=len(tags))
    return _tags_to_response(tags)


@router.get("/search", response_model=list[TagResponse])
async def search_tags(
    q: Annotated[str, Query(description="Tag name search query")],
    current_user: Annotated[User, Depends(get_current_user)],
    client: Annotated[PaperlessClient, Depends(get_paperless_client)],
) -> list[TagResponse]:
    """
    Search tags by name.

    Proxies the request to the Paperless API with a name filter.
    """
    tags = await client.search_tags(q)
    logger.debug("tags_searched", query=q, count=len(tags))
    return _tags_to_response(tags)
