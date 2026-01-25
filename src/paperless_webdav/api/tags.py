# src/paperless_webdav/api/tags.py
"""Tags API endpoints - proxies tag operations to Paperless-ngx."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from paperless_webdav.auth import AuthenticatedUser, get_current_user
from paperless_webdav.config import get_settings
from paperless_webdav.logging import get_logger
from paperless_webdav.paperless_client import PaperlessClient, PaperlessTag
from paperless_webdav.schemas import TagResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tags", tags=["tags"])


def _tags_to_response(tags: list[PaperlessTag]) -> list[TagResponse]:
    """Convert PaperlessTag objects to TagResponse schemas."""
    return [TagResponse(id=tag.id, name=tag.name, slug=tag.slug, color=tag.color) for tag in tags]


def get_paperless_client(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> PaperlessClient:
    """Get a PaperlessClient instance for the current authenticated user.

    Note: PaperlessClient uses context managers internally for HTTP requests,
    so it doesn't need explicit cleanup.
    """
    settings = get_settings()
    return PaperlessClient(base_url=settings.paperless_url, token=current_user.token)


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=list[TagResponse])
async def list_tags(
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
    client: Annotated[PaperlessClient, Depends(get_paperless_client)],
) -> list[TagResponse]:
    """
    Search tags by name.

    Proxies the request to the Paperless API with a name filter.
    """
    tags = await client.search_tags(q)
    logger.debug("tags_searched", query=q, count=len(tags))
    return _tags_to_response(tags)
