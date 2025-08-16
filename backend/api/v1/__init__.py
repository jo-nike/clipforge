"""
API v1 Router - Main router for all v1 API endpoints
Combines all API routes with proper structure and documentation
"""

from typing import Any, Dict

from api.dependencies import check_service_health, get_metrics_summary, setup_request_context
from api.metrics_endpoint import metrics_router
from api.v1.auth import router as auth_router
from api.v1.clips import router as clips_router
from api.v1.sessions import router as sessions_router
from api.v1.storage import router as storage_router
from core.config import settings
from core.logging import get_logger
from fastapi import APIRouter, Depends

logger = get_logger("api_v1")

# Create the main v1 router
v1_router = APIRouter(prefix="/api/v1")

# Include all sub-routers
v1_router.include_router(auth_router)
v1_router.include_router(clips_router)
v1_router.include_router(sessions_router)
v1_router.include_router(storage_router)
v1_router.include_router(metrics_router)


# Health check endpoint at the v1 level
@v1_router.get("/health")
async def health_check(_: str = Depends(setup_request_context)) -> Dict[str, Any]:
    """Comprehensive health check endpoint for v1 API"""
    try:
        logger.debug("Performing health check")

        service_health = await check_service_health()

        health_status = {
            "status": "healthy",
            "service": settings.app_name,
            "version": settings.app_version,
            "api_version": "v1",
            **service_health,
        }

        # Use the health service's status determination
        if service_health.get("status") != "healthy":
            health_status["status"] = "unhealthy"

        if health_status["status"] != "healthy":
            logger.warning(f"Health check failed: {health_status}")
        else:
            logger.debug("Health check passed")

        return health_status

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "service": settings.app_name,
            "version": settings.app_version,
            "api_version": "v1",
            "error": str(e),
        }


# Alternative health endpoint path
@v1_router.get("/api/health")
async def alt_health_check(
    _: str = Depends(setup_request_context),
) -> Dict[str, Any]:
    """Alternative health check endpoint path"""
    return await health_check()


# Metrics endpoint for monitoring
@v1_router.get("/metrics")
async def get_performance_metrics(
    _: str = Depends(setup_request_context),
) -> Dict[str, Any]:
    """Get performance metrics for monitoring and alerting"""
    try:
        logger.debug("Retrieving performance metrics")
        metrics = await get_metrics_summary()
        return metrics
    except Exception as e:
        logger.error(f"Failed to retrieve metrics: {e}")
        return {"error": "Failed to retrieve metrics", "timestamp": "unknown"}


# Export the router
__all__ = ["v1_router"]
