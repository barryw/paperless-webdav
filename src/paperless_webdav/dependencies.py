# src/paperless_webdav/dependencies.py
"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from paperless_webdav.database import get_session


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session.

    Yields:
        AsyncSession instance for database operations.
    """
    async for session in get_session():
        yield session


async def get_db_session_optional() -> AsyncGenerator[AsyncSession | None, None]:
    """Dependency to get database session, or None if not available.

    Yields None if database is not initialized (during startup or if connection fails).
    Useful for health checks that need to handle database unavailability gracefully.
    """
    try:
        async for session in get_session():
            yield session
    except RuntimeError:
        # Database not initialized yet
        yield None
