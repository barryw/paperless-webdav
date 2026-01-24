"""Health check endpoints for liveness and readiness probes."""

from fastapi import APIRouter, Response

from paperless_webdav.logging import get_logger

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
async def readiness_check(response: Response) -> dict:
    """
    Readiness probe endpoint.

    Returns 200 if the application is ready to serve traffic.
    Checks database connectivity and other dependencies.
    Returns 503 if not ready.
    """
    # TODO: Implement actual database connectivity check in Task 2.6
    checks = {
        "database": False,
        "paperless": False,
    }

    all_ready = all(checks.values())

    if not all_ready:
        response.status_code = 503
        logger.warning("readiness_check_failed", checks=checks)

    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": checks,
    }
