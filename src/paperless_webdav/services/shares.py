# src/paperless_webdav/services/shares.py
"""Share service with database operations."""

from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from paperless_webdav.logging import get_logger
from paperless_webdav.models import Share, User
from paperless_webdav.schemas import ShareCreate, ShareUpdate

logger = get_logger(__name__)


async def get_or_create_user(session: AsyncSession, external_id: str) -> User:
    """Get or create a user by external_id.

    Args:
        session: Database session.
        external_id: External user identifier (username from auth provider).

    Returns:
        User instance (existing or newly created).
    """
    stmt = select(User).where(User.external_id == external_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(external_id=external_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info("user_created", external_id=external_id)

    return user


async def _get_owner_external_id(session: AsyncSession, owner_id: UUID) -> str | None:
    """Get external_id for a user by their ID.

    Args:
        session: Database session.
        owner_id: User UUID.

    Returns:
        external_id string or None if not found.
    """
    stmt = select(User.external_id).where(User.id == owner_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def is_share_owner(session: AsyncSession, share: Share, username: str) -> bool:
    """Check if a user is the owner of a share.

    Args:
        session: Database session.
        share: Share instance.
        username: External user identifier.

    Returns:
        True if user is the owner, False otherwise.
    """
    owner_external_id = await _get_owner_external_id(session, share.owner_id)
    return owner_external_id == username


async def get_user_shares(session: AsyncSession, username: str) -> list[Share]:
    """Get all shares accessible to a user.

    Returns shares where:
    - User is the owner, OR
    - User is in allowed_users list

    Args:
        session: Database session.
        username: External user identifier.

    Returns:
        List of Share instances.
    """
    # First get the user (if exists)
    user_stmt = select(User).where(User.external_id == username)
    user_result = await session.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if user is None:
        # User doesn't exist, check for shares by allowed_users only
        # (edge case - user might be allowed but never logged in)
        stmt = select(Share).where(Share.allowed_users.contains([username]))
    else:
        # User exists, check both owned shares and allowed shares
        stmt = select(Share).where(
            or_(
                Share.owner_id == user.id,
                Share.allowed_users.contains([username]),
            )
        )

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_share_by_name(session: AsyncSession, name: str, username: str) -> Share | None:
    """Get a share by name if accessible to the user.

    Args:
        session: Database session.
        name: Share name.
        username: External user identifier.

    Returns:
        Share instance if found and accessible, None otherwise.
    """
    stmt = select(Share).where(Share.name == name)
    result = await session.execute(stmt)
    share = result.scalar_one_or_none()

    if share is None:
        return None

    # Check if user has access
    owner_external_id = await _get_owner_external_id(session, share.owner_id)

    if owner_external_id == username:
        return share

    if username in (share.allowed_users or []):
        return share

    return None


async def create_share(session: AsyncSession, username: str, share_data: ShareCreate) -> Share:
    """Create a new share.

    Args:
        session: Database session.
        username: External user identifier (will be owner).
        share_data: Share creation data.

    Returns:
        Created Share instance.
    """
    # Get or create the user
    user = await get_or_create_user(session, username)

    # Create the share
    share = Share(
        name=share_data.name,
        owner_id=user.id,
        include_tags=share_data.include_tags,
        exclude_tags=share_data.exclude_tags,
        expires_at=share_data.expires_at,
        read_only=share_data.read_only,
        done_folder_enabled=share_data.done_folder_enabled,
        done_folder_name=share_data.done_folder_name,
        done_tag=share_data.done_tag,
        allowed_users=share_data.allowed_users,
    )

    session.add(share)
    await session.commit()
    await session.refresh(share)

    logger.info("share_created", share_name=share.name, owner=username)
    return share


async def update_share(
    session: AsyncSession, share_id: UUID, share_data: ShareUpdate
) -> Share | None:
    """Update an existing share.

    Args:
        session: Database session.
        share_id: Share UUID.
        share_data: Share update data.

    Returns:
        Updated Share instance or None if not found.
    """
    stmt = select(Share).where(Share.id == share_id)
    result = await session.execute(stmt)
    share = result.scalar_one_or_none()

    if share is None:
        return None

    # Update only fields that are set (not None)
    update_data = share_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(share, field, value)

    await session.commit()
    await session.refresh(share)

    logger.info("share_updated", share_id=str(share_id))
    return share


async def delete_share(session: AsyncSession, name: str, username: str) -> bool:
    """Delete a share.

    Only the owner can delete a share.

    Args:
        session: Database session.
        name: Share name.
        username: External user identifier.

    Returns:
        True if deleted, False if not found or not authorized.
    """
    # Get the user
    user_stmt = select(User).where(User.external_id == username)
    user_result = await session.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if user is None:
        return False

    # Get the share and verify ownership
    share_stmt = select(Share).where(Share.name == name)
    share_result = await session.execute(share_stmt)
    share = share_result.scalar_one_or_none()

    if share is None:
        return False

    if share.owner_id != user.id:
        return False

    await session.delete(share)
    await session.commit()

    logger.info("share_deleted", share_name=name, owner=username)
    return True


async def check_db_connectivity(session: AsyncSession) -> bool:
    """Check if database is accessible.

    Args:
        session: Database session.

    Returns:
        True if database is accessible, False otherwise.
    """
    try:
        await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("database_connectivity_check_failed", error=str(e))
        return False
