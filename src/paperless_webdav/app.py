"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from paperless_webdav.api.health import router as health_router
from paperless_webdav.api.shares import router as shares_router
from paperless_webdav.api.tags import router as tags_router
from paperless_webdav.config import get_settings
from paperless_webdav.logging import setup_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)
    logger.info("application_starting", admin_port=settings.admin_port)

    # TODO: Initialize database in Task 2.6
    # TODO: Initialize Paperless client

    yield

    # Cleanup
    logger.info("application_stopping")
    # TODO: Close database connections


def create_app() -> FastAPI:
    """
    Application factory for FastAPI.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="Paperless WebDAV Bridge",
        description="WebDAV bridge for Paperless-ngx with tag-based shares",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health_router)
    app.include_router(shares_router)
    app.include_router(tags_router)

    return app


# For direct uvicorn usage
app = create_app()
