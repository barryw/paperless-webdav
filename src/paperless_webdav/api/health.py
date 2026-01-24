"""Health check endpoints for liveness and readiness probes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from paperless_webdav.dependencies import get_db_session_optional
from paperless_webdav.logging import get_logger
from paperless_webdav.services.shares import check_db_connectivity

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """
    Liveness probe endpoint.

    Returns 200 if the application is running.
    Used by container orchestrators to determine if the service is alive.
    """
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check(
    response: Response,
    session: Annotated[AsyncSession | None, Depends(get_db_session_optional)] = None,
) -> dict:
    """
    Readiness probe endpoint.

    Returns 200 if the application is ready to serve traffic.
    Checks database connectivity and other dependencies.
    Returns 503 if not ready.
    """
    # Check database connectivity
    db_connected = False
    if session is not None:
        db_connected = await check_db_connectivity(session)

    checks = {
        "database": db_connected,
        "paperless": False,  # TODO: Implement in future task
    }

    all_ready = all(checks.values())

    if not all_ready:
        response.status_code = 503
        logger.warning("readiness_check_failed", checks=checks)

    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": checks,
    }
