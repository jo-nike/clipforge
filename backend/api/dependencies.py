"""
FastAPI Dependencies - Dependency injection for services and authentication
Provides clean separation of concerns and testable service injection
"""

from typing import Any, Dict, Optional

from core.logging import get_logger, set_correlation_id
from domain.schemas import PlexUser
from fastapi import Depends, HTTPException, Request, status
from infrastructure.database import get_db_session
from infrastructure.repositories import (
    ClipRepository,
    EditRepository,
    SnapshotRepository,
    UserRepository,
)
from services.auth_service import get_current_user, get_plex_token
from services.clip_service import ClipProcessingService
from services.plex_service import PlexService
from services.secure_storage_service import SecureStorageService

logger = get_logger("dependencies")


# Service Dependencies
def get_clip_processing_service() -> ClipProcessingService:
    """Get clip processing service instance"""
    return ClipProcessingService()


def get_plex_service() -> PlexService:
    """Get Plex service instance"""
    return PlexService()


def get_storage_service() -> SecureStorageService:
    """Get secure storage service instance"""
    return SecureStorageService()


# Repository Dependencies
def get_user_repository() -> UserRepository:
    """Get user repository with database session"""
    with get_db_session() as db:
        return UserRepository(db)


def get_clip_repository() -> ClipRepository:
    """Get clip repository with database session"""
    with get_db_session() as db:
        return ClipRepository(db)


def get_edit_repository() -> EditRepository:
    """Get edit repository with database session"""
    with get_db_session() as db:
        return EditRepository(db)


def get_snapshot_repository() -> SnapshotRepository:
    """Get snapshot repository with database session"""
    with get_db_session() as db:
        return SnapshotRepository(db)


# Request Context Dependencies
async def setup_request_context(request: Request) -> str:
    """Set up request context and correlation ID"""
    # Get or generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID")
    if not correlation_id:
        correlation_id = set_correlation_id()
    else:
        set_correlation_id(correlation_id)

    logger.debug(
        f"Request {request.method} {request.url.path}",
        extra={"correlation_id": correlation_id},
    )

    return correlation_id


# Authentication Dependencies (using existing secure system)
async def get_authenticated_user(
    current_user: PlexUser = Depends(get_current_user),
) -> PlexUser:
    """Get authenticated user with proper error handling"""
    return current_user


async def get_authenticated_user_with_plex_token(
    current_user: PlexUser = Depends(get_current_user),
    plex_token: Optional[str] = Depends(get_plex_token),
) -> tuple[PlexUser, Optional[str]]:
    """Get authenticated user and their Plex token"""
    if not plex_token:
        logger.warning(f"No Plex token available for user {current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to retrieve Plex token",
        )

    return current_user, plex_token


# Validation Dependencies
def validate_pagination(page: int = 1, page_size: int = 20) -> Dict[str, int]:
    """Validate and normalize pagination parameters"""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    offset = (page - 1) * page_size

    return {"page": page, "page_size": page_size, "offset": offset}


def validate_quality(quality: str = "medium") -> str:
    """Validate quality parameter"""
    valid_qualities = ["low", "medium", "high"]
    if quality not in valid_qualities:
        return "medium"
    return quality


def validate_format(format_type: str = "mp4") -> str:
    """Validate format parameter"""
    valid_formats = ["mp4", "mkv", "avi", "webm"]
    if format_type not in valid_formats:
        return "mp4"
    return format_type


def validate_image_format(format_type: str = "jpg") -> str:
    """Validate image format parameter"""
    valid_formats = ["jpg", "png", "webp"]
    if format_type not in valid_formats:
        return "jpg"
    return format_type


# Service Factory Dependencies
class ServiceFactory:
    """Factory for creating service instances with proper dependency injection"""

    def __init__(self) -> None:
        self._clip_service: Optional[ClipProcessingService] = None
        self._plex_service: Optional[PlexService] = None
        self._storage_service: Optional[SecureStorageService] = None

    @property
    def clip_service(self) -> ClipProcessingService:
        """Get or create clip processing service"""
        if self._clip_service is None:
            self._clip_service = ClipProcessingService()
        return self._clip_service

    @property
    def plex_service(self) -> PlexService:
        """Get or create Plex service"""
        if self._plex_service is None:
            self._plex_service = PlexService()
        return self._plex_service

    @property
    def storage_service(self) -> SecureStorageService:
        """Get or create storage service"""
        if self._storage_service is None:
            self._storage_service = SecureStorageService()
        return self._storage_service


# Global service factory instance
service_factory = ServiceFactory()


def get_service_factory() -> ServiceFactory:
    """Get the global service factory"""
    return service_factory


# Health Check Dependencies
async def check_service_health() -> Dict[str, Any]:
    """Check health of all services using the comprehensive health service"""
    from services.health_service import health_service

    return await health_service.get_comprehensive_health()


async def get_metrics_summary() -> Dict[str, Any]:
    """Get performance metrics summary"""
    from services.health_service import health_service

    return await health_service.get_metrics_summary()


def record_request_metrics(
    response_time_ms: float, status_code: int, endpoint: str = "unknown"
) -> None:
    """Record request metrics for monitoring"""
    from api.metrics_endpoint import record_request_metric
    from services.health_service import health_service

    # Record in both health service and metrics endpoint
    health_service.record_request(response_time_ms, status_code)
    record_request_metric(response_time_ms, status_code, endpoint)


# Error Handler Dependencies
def handle_service_error(e: Exception) -> HTTPException:
    """Convert service exceptions to HTTP exceptions"""
    from core.exceptions import (
        AuthenticationError,
        AuthorizationError,
        ClipForgeException,
        ClipNotFoundError,
        ClipProcessingError,
        FileNotFoundError,
        PlexConnectionError,
        StorageError,
        ValidationError,
    )

    if isinstance(e, AuthenticationError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)
    elif isinstance(e, AuthorizationError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    elif isinstance(e, ValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    elif isinstance(e, (ClipNotFoundError, FileNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    elif isinstance(e, (ClipProcessingError, StorageError)):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)
    elif isinstance(e, PlexConnectionError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=e.message)
    elif isinstance(e, ClipForgeException):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)
    else:
        logger.error(f"Unhandled exception: {e}")
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )
