# src/paperless_webdav/database.py
"""Database connection and session management."""

from collections.abc import AsyncGenerator
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Engine and session factory (initialized on startup)
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None

# Sync engine for cross-thread access (WebDAV)
_sync_engine = None
_sync_session_factory: sessionmaker | None = None
_database_url: str | None = None


async def init_database(database_url: str) -> None:
    """Initialize database engine and session factory."""
    global _engine, _async_session_factory, _database_url

    _database_url = database_url

    async_url = database_url
    if async_url.startswith("postgresql://"):
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    _engine = create_async_engine(async_url, echo=False, pool_pre_ping=True)
    _async_session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )

    # Import models to register them with Base before creating tables
    from paperless_webdav import models  # noqa: F401

    # Create all tables with advisory lock to prevent race conditions
    # when multiple replicas start simultaneously
    async with _engine.begin() as conn:
        # Acquire advisory lock (lock_id=1 for schema migrations)
        await conn.execute(text("SELECT pg_advisory_lock(1)"))
        try:
            await conn.run_sync(Base.metadata.create_all)
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(1)"))


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for dependency injection."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database first.")
    async with _async_session_factory() as session:
        yield session


async def close_database() -> None:
    """Close database connections."""
    global _engine, _sync_engine
    if _engine:
        await _engine.dispose()
        _engine = None
    if _sync_engine:
        _sync_engine.dispose()
        _sync_engine = None


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Get a synchronous database session for cross-thread access.

    This is used by the WebDAV server which runs in a separate thread
    and cannot share the async engine's event loop.
    """
    global _sync_engine, _sync_session_factory

    if _database_url is None:
        raise RuntimeError("Database not initialized. Call init_database first.")

    # Lazily create sync engine on first use
    if _sync_engine is None:
        sync_url = _database_url
        if sync_url.startswith("postgresql://"):
            sync_url = sync_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif sync_url.startswith("postgresql+asyncpg://"):
            sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        _sync_engine = create_engine(sync_url, echo=False, pool_pre_ping=True)
        _sync_session_factory = sessionmaker(_sync_engine, expire_on_commit=False)

    if _sync_session_factory is None:
        raise RuntimeError("Sync session factory not initialized.")

    with _sync_session_factory() as session:
        yield session
