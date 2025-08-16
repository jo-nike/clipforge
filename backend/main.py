"""
ClipForge Application - Service-oriented architecture
Phase 2 implementation with proper service layer, dependency injection, and structured logging
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from api.middleware import setup_middleware

# API imports
from api.v1 import v1_router

# Core imports
from core.config import settings
from core.exceptions import ClipForgeException
from core.logging import get_logger, set_correlation_id, setup_logging
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Infrastructure imports
from infrastructure.database import init_database

# Setup logging first
setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager - handles startup and shutdown"""
    # Startup
    logger.info("Initializing database...")
    init_database()

    # Initialize cache service
    logger.info("Initializing cache service...")
    from services.cache_service import startup_cache

    await startup_cache()

    logger.info("ClipForge API initialized successfully")
    logger.info("Service layer architecture active with:")
    logger.info("- Structured logging with correlation IDs")
    logger.info("- Dependency injection for services")
    logger.info("- Comprehensive error handling")
    logger.info("- Security middleware stack")
    logger.info("- Database connection pooling")
    logger.info("- In-memory caching layer")

    yield

    # Shutdown
    logger.info("ClipForge API shutting down")
    from services.cache_service import shutdown_cache

    await shutdown_cache()


# Create FastAPI app with enhanced configuration
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ClipForge API - Service-oriented architecture with secure video clip creation from Plex media",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

# Setup security middleware (includes CORS, rate limiting, etc.)
setup_middleware(app)


# Add request correlation ID middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next: Callable) -> Any:
    """Add correlation ID to all requests for tracing"""
    correlation_id = request.headers.get("X-Correlation-ID")
    if not correlation_id:
        correlation_id = set_correlation_id()
    else:
        set_correlation_id(correlation_id)

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


# Add global exception handler
@app.exception_handler(ClipForgeException)
async def clipforge_exception_handler(request: Request, exc: ClipForgeException) -> JSONResponse:
    """Global exception handler for ClipForge exceptions"""
    logger.error(
        f"ClipForge exception: {exc.message}",
        extra={"error_code": exc.error_code, "details": exc.details},
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )


# Include API routers
app.include_router(v1_router)

# Frontend paths
project_root = Path(__file__).parent.parent
frontend_path = project_root / "frontend"


# Frontend route handlers
@app.get("/")
async def serve_index() -> Any:
    """Serve the main application page"""
    if frontend_path.exists():
        index_path = frontend_path / "index.html"
        if index_path.exists():
            logger.debug("Serving index.html")
            return FileResponse(str(index_path))

    logger.info("Frontend not found, returning API info")
    return {
        "message": f"{settings.app_name} API is running",
        "version": settings.app_version,
        "api_version": "v1",
        "documentation": ("/docs" if settings.debug else "Documentation disabled in production"),
    }


@app.get("/login")
async def serve_login() -> Any:
    """Serve the login page"""
    if frontend_path.exists():
        login_path = frontend_path / "login.html"
        if login_path.exists():
            logger.debug("Serving login.html")
            return FileResponse(str(login_path))

    return {"message": "Login page not found", "api_endpoint": "/api/v1/auth/signin"}


# Health endpoint
@app.get("/api/health")
async def health() -> Any:
    """Health endpoint"""
    from api.v1 import health_check

    return await health_check()


# Mount static files if frontend exists
if frontend_path.exists():
    static_path = frontend_path / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
        logger.info(f"Frontend static files mounted from: {static_path}")
    else:
        logger.warning(f"Frontend static directory not found: {static_path}")
else:
    logger.warning(f"Frontend directory not found: {frontend_path}")

# Log startup information
logger.info("ClipForge starting with service-oriented architecture:")
logger.info(f"- Storage path: {settings.absolute_clips_path}")
logger.info(f"- CORS origins: {settings.cors_origins}")
logger.info(f"- Rate limiting: {settings.rate_limit_requests} req/{settings.rate_limit_window}s")
logger.info(f"- Debug mode: {settings.debug}")
logger.info(f"- Log level: {settings.log_level}")

# Event handlers moved to lifespan context manager above

if __name__ == "__main__":
    import uvicorn

    # Configure uvicorn logging
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {
                "handlers": ["default"],
                "level": "INFO" if settings.debug else "WARNING",
            },
        },
    }

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_config=log_config,
    )
