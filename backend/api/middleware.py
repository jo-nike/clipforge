"""
Security middleware for ClipForge
Handles CORS, rate limiting, request tracking, and security headers
"""

import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional

from core.config import settings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Context variable for request tracking
request_context: Dict[str, str] = {}


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware for request tracking and logging"""

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Store request context
        request_context["request_id"] = request_id
        request_context["user_agent"] = request.headers.get("user-agent", "unknown")
        request_context["client_ip"] = self._get_client_ip(request)

        # Log request start
        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request_context["client_ip"],
                "user_agent": request_context["user_agent"],
            },
        )

        try:
            response = await call_next(request)

            # Calculate request duration
            duration = time.time() - start_time
            duration_ms = round(duration * 1000, 2)

            # Record metrics for health monitoring
            try:
                from api.dependencies import record_request_metrics

                record_request_metrics(duration_ms, response.status_code)
            except ImportError:
                pass  # Health service not available

            # Log successful request
            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration = time.time() - start_time
            duration_ms = round(duration * 1000, 2)

            # Record error metrics for health monitoring
            try:
                from api.dependencies import record_request_metrics

                record_request_metrics(duration_ms, 500)  # Assume 500 for unhandled exceptions
            except ImportError:
                pass  # Health service not available

            # Log failed request
            logger.error(
                f"Request failed: {str(e)}",
                extra={
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise
        finally:
            # Clear request context
            request_context.clear()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request headers"""
        # Check for forwarded headers (reverse proxy)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to direct connection
        if request.client:
            return request.client.host

        return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiting middleware"""

    def __init__(
        self,
        app: Any,
        requests_per_window: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> None:
        super().__init__(app)
        self.requests_per_window = requests_per_window or settings.rate_limit_requests
        self.window_seconds = window_seconds or settings.rate_limit_window

        # Storage for rate limit data: {client_ip: deque of request timestamps}
        self.request_history: Dict[str, deque] = defaultdict(lambda: deque())

        logger.info(
            f"Rate limiting initialized: {self.requests_per_window} requests per {self.window_seconds}s"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        client_ip = self._get_client_ip(request)
        current_time = time.time()

        # Skip rate limiting for health checks
        if request.url.path == "/api/health":
            return await call_next(request)

        # Check rate limit
        if not self._is_request_allowed(client_ip, current_time):
            logger.warning(
                f"Rate limit exceeded for {client_ip}",
                extra={
                    "client_ip": client_ip,
                    "path": request.url.path,
                    "method": request.method,
                },
            )

            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Maximum {self.requests_per_window} requests per {self.window_seconds} seconds",
                    "retry_after": self.window_seconds,
                },
                headers={
                    "Retry-After": str(self.window_seconds),
                    "X-RateLimit-Limit": str(self.requests_per_window),
                    "X-RateLimit-Window": str(self.window_seconds),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        remaining_requests = self._get_remaining_requests(client_ip, current_time)
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining_requests)
        response.headers["X-RateLimit-Window"] = str(self.window_seconds)

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP for rate limiting"""
        # Check for forwarded headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host

        return "unknown"

    def _is_request_allowed(self, client_ip: str, current_time: float) -> bool:
        """Check if request is allowed under rate limit"""
        request_times = self.request_history[client_ip]

        # Remove old requests outside the window
        cutoff_time = current_time - self.window_seconds
        while request_times and request_times[0] <= cutoff_time:
            request_times.popleft()

        # Check if we're under the limit
        if len(request_times) < self.requests_per_window:
            # Add current request time
            request_times.append(current_time)
            return True

        return False

    def _get_remaining_requests(self, client_ip: str, current_time: float) -> int:
        """Get remaining requests for client"""
        request_times = self.request_history[client_ip]

        # Remove old requests outside the window
        cutoff_time = current_time - self.window_seconds
        while request_times and request_times[0] <= cutoff_time:
            request_times.popleft()

        return max(0, self.requests_per_window - len(request_times))


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding security headers"""

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        response = await call_next(request)

        # Security headers
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

        # Add HTTPS security headers in production
        if settings.secure_cookies:
            security_headers.update(
                {
                    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'",
                }
            )

        # Apply headers
        for header, value in security_headers.items():
            response.headers[header] = value

        return response


def setup_middleware(app: FastAPI) -> None:
    """
    Configure all middleware for the application

    Args:
        app: FastAPI application instance
    """
    # Import middleware components
    from api.csrf_middleware import APIKeyMiddleware, CSRFMiddleware
    from api.validation_middleware import RequestValidationMiddleware, TimeoutMiddleware

    # Security headers (first, applied to all responses)
    app.add_middleware(SecurityHeadersMiddleware)

    # Request validation and timeout (early in pipeline)
    app.add_middleware(
        RequestValidationMiddleware,
        max_request_size=50 * 1024 * 1024,  # 50MB
        max_json_depth=10,
        max_file_size=settings.max_clip_size_mb * 1024 * 1024,
    )

    app.add_middleware(
        TimeoutMiddleware,
        timeout_seconds=settings.plex_timeout + 10,  # Plex timeout + buffer
    )

    # CSRF and API key protection
    app.add_middleware(CSRFMiddleware)  # Re-enabled with hybrid approach
    app.add_middleware(APIKeyMiddleware)

    # Rate limiting (before request processing)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_window=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window,
    )

    # Request tracking (for logging and debugging)
    app.add_middleware(RequestTrackingMiddleware)

    # CORS (last, to handle preflight requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-CSRF-Token",
        ],
    )

    logger.info("Middleware configuration completed")
    logger.info(f"CORS origins configured: {settings.cors_origins}")
    logger.info(
        f"Rate limiting: {settings.rate_limit_requests} requests per {settings.rate_limit_window}s"
    )
    logger.info("Request validation, timeout, hybrid CSRF, and API key middleware enabled")


@contextmanager
def get_request_context() -> Any:
    """Context manager for accessing request-scoped data"""
    yield request_context
