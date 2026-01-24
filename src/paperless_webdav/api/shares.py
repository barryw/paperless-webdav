# src/paperless_webdav/api/shares.py
"""Share CRUD API endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from paperless_webdav.auth import AuthenticatedUser, get_current_user
from paperless_webdav.dependencies import get_db_session
from paperless_webdav.logging import get_logger
from paperless_webdav.models import Share
from paperless_webdav.schemas import ShareCreate, ShareResponse, ShareUpdate
from paperless_webdav.services import shares as share_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/shares", tags=["shares"])


# =============================================================================
# Service Function Wrappers (for easy mocking in tests)
# =============================================================================


async def get_user_shares(session: AsyncSession, username: str) -> list[Share]:
    """Get all shares owned by or accessible to the user."""
    return await share_service.get_user_shares(session, username)


async def get_share_by_name(session: AsyncSession, name: str, username: str) -> Share | None:
    """Get a share by name if accessible to user."""
    return await share_service.get_share_by_name(session, name, username)


async def is_share_owner(session: AsyncSession, share: Share, username: str) -> bool:
    """Check if user is the owner of a share."""
    return await share_service.is_share_owner(session, share, username)


async def create_share(session: AsyncSession, username: str, share_data: ShareCreate) -> Share:
    """Create a new share."""
    return await share_service.create_share(session, username, share_data)


async def update_share(
    session: AsyncSession, share_id: UUID, share_data: ShareUpdate
) -> Share | None:
    """Update an existing share."""
    return await share_service.update_share(session, share_id, share_data)


async def delete_share(session: AsyncSession, name: str, username: str) -> bool:
    """Delete a share."""
    return await share_service.delete_share(session, name, username)


async def audit_log(
    event_type: str,
    username: str | None = None,
    share_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Log an audit event.

    TODO: Wire to database audit log in a future task.
    """
    logger.info(
        "audit_event",
        event_type=event_type,
        username=username,
        share_id=str(share_id) if share_id else None,
        details=details,
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=list[ShareResponse])
async def list_shares(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ShareResponse]:
    """
    List all shares accessible to the current user.

    Returns shares owned by or shared with the user.
    """
    shares = await get_user_shares(session, current_user.username)
    logger.debug("shares_listed", username=current_user.username, count=len(shares))
    return [ShareResponse.model_validate(share) for share in shares]


@router.post("", response_model=ShareResponse, status_code=status.HTTP_201_CREATED)
async def create_share_endpoint(
    share_data: ShareCreate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ShareResponse:
    """
    Create a new share.

    The current user becomes the owner of the share.
    """
    # Check if share with this name already exists
    existing = await get_share_by_name(session, share_data.name, current_user.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Share with name '{share_data.name}' already exists",
        )

    share = await create_share(session, current_user.username, share_data)

    await audit_log(
        event_type="share_created",
        username=current_user.username,
        share_id=share.id,
        details={"name": share_data.name},
    )

    logger.info("share_created", username=current_user.username, share_name=share_data.name)
    return ShareResponse.model_validate(share)


@router.get("/{name}", response_model=ShareResponse)
async def get_share(
    name: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ShareResponse:
    """
    Get a specific share by name.

    Returns 404 if the share doesn't exist or is not accessible to the user.
    """
    share = await get_share_by_name(session, name, current_user.username)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Share '{name}' not found",
        )
    return ShareResponse.model_validate(share)


@router.put("/{name}", response_model=ShareResponse)
async def update_share_endpoint(
    name: str,
    share_data: ShareUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ShareResponse:
    """
    Update an existing share.

    Only the owner can update a share.
    """
    share = await get_share_by_name(session, name, current_user.username)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Share '{name}' not found",
        )

    # Only the owner can update a share
    if not await is_share_owner(session, share, current_user.username):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can update a share",
        )

    updated_share = await update_share(session, share.id, share_data)

    await audit_log(
        event_type="share_updated",
        username=current_user.username,
        share_id=share.id,
        details={"name": name, "updates": share_data.model_dump(exclude_unset=True)},
    )

    logger.info("share_updated", username=current_user.username, share_name=name)
    return ShareResponse.model_validate(updated_share)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share_endpoint(
    name: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """
    Delete a share.

    Only the owner can delete a share.
    """
    deleted = await delete_share(session, name, current_user.username)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Share '{name}' not found",
        )

    await audit_log(
        event_type="share_deleted",
        username=current_user.username,
        details={"name": name},
    )

    logger.info("share_deleted", username=current_user.username, share_name=name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
