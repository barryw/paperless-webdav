# src/paperless_webdav/api/shares.py
"""Share CRUD API endpoints."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from paperless_webdav.auth import AuthenticatedUser, get_current_user
from paperless_webdav.logging import get_logger
from paperless_webdav.schemas import ShareCreate, ShareResponse, ShareUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/api/shares", tags=["shares"])


class Share:
    """Placeholder share type for database operations."""

    id: UUID
    name: str
    owner_id: UUID
    include_tags: list[str]
    exclude_tags: list[str]
    expires_at: datetime | None
    read_only: bool
    done_folder_enabled: bool
    done_folder_name: str
    done_tag: str | None
    allowed_users: list[str]
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Placeholder functions (to be wired to real implementations in Task 2.6)
# =============================================================================


async def get_user_shares(username: str) -> list[Share]:
    """
    Placeholder: Get all shares owned by or accessible to the user.

    Will be wired to database in Task 2.6.
    """
    return []


async def get_share_by_name(name: str, username: str) -> Share | None:
    """
    Placeholder: Get a share by name if accessible to user.

    Will be wired to database in Task 2.6.
    """
    return None


async def create_share(username: str, share_data: ShareCreate) -> Share:
    """
    Placeholder: Create a new share.

    Will be wired to database in Task 2.6.
    """
    raise NotImplementedError("Database not connected")


async def update_share(share_id: UUID, share_data: ShareUpdate) -> Share:
    """
    Placeholder: Update an existing share.

    Will be wired to database in Task 2.6.
    """
    raise NotImplementedError("Database not connected")


async def delete_share(name: str, username: str) -> bool:
    """
    Placeholder: Delete a share.

    Will be wired to database in Task 2.6.
    """
    raise NotImplementedError("Database not connected")


async def audit_log(
    event_type: str,
    username: str | None = None,
    share_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Placeholder: Log an audit event.

    Will be wired to database in Task 2.6.
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
) -> list[ShareResponse]:
    """
    List all shares accessible to the current user.

    Returns shares owned by or shared with the user.
    """
    shares = await get_user_shares(current_user.username)
    logger.debug("shares_listed", username=current_user.username, count=len(shares))
    return [ShareResponse.model_validate(share) for share in shares]


@router.post("", response_model=ShareResponse, status_code=status.HTTP_201_CREATED)
async def create_share_endpoint(
    share_data: ShareCreate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ShareResponse:
    """
    Create a new share.

    The current user becomes the owner of the share.
    """
    # Check if share with this name already exists
    existing = await get_share_by_name(share_data.name, current_user.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Share with name '{share_data.name}' already exists",
        )

    share = await create_share(current_user.username, share_data)

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
) -> ShareResponse:
    """
    Get a specific share by name.

    Returns 404 if the share doesn't exist or is not accessible to the user.
    """
    share = await get_share_by_name(name, current_user.username)
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
) -> ShareResponse:
    """
    Update an existing share.

    Only the owner can update a share.
    """
    share = await get_share_by_name(name, current_user.username)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Share '{name}' not found",
        )

    updated_share = await update_share(share.id, share_data)

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
) -> Response:
    """
    Delete a share.

    Only the owner can delete a share.
    """
    deleted = await delete_share(name, current_user.username)
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
