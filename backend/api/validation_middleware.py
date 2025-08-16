"""
Request validation middleware for ClipForge
Handles request size limits, content validation, and file upload validation
"""

import json
import logging
from typing import Any, Optional

from core.config import settings
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for validating incoming requests"""

    def __init__(
        self,
        app: Any,
        max_request_size: Optional[int] = None,
        max_json_depth: int = 10,
        max_file_size: Optional[int] = None,
    ):
        super().__init__(app)
        self.max_request_size = max_request_size or (50 * 1024 * 1024)  # 50MB default
        self.max_json_depth = max_json_depth
        self.max_file_size = max_file_size or (settings.max_clip_size_mb * 1024 * 1024)

        logger.info(
            f"Request validation initialized: max_size={self.max_request_size}B, "
            f"max_file_size={self.max_file_size}B, max_json_depth={self.max_json_depth}"
        )

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Validate incoming requests"""

        # Check request size
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_request_size:
                    logger.warning(
                        f"Request size too large: {size} bytes (max: {self.max_request_size})",
                        extra={
                            "client_ip": self._get_client_ip(request),
                            "path": request.url.path,
                            "request_size": size,
                        },
                    )
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "Request too large",
                            "message": f"Request size {size} bytes exceeds maximum of {self.max_request_size} bytes",
                            "max_size": self.max_request_size,
                        },
                    )
            except ValueError:
                logger.warning(
                    f"Invalid content-length header: {content_length}",
                    extra={
                        "client_ip": self._get_client_ip(request),
                        "path": request.url.path,
                    },
                )

        # Validate file uploads for multipart requests
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            try:
                await self._validate_multipart_request(request)
            except HTTPException as e:
                return JSONResponse(
                    status_code=e.status_code,
                    content={"error": e.detail, "type": "validation_error"},
                )

        # Validate JSON content for JSON requests
        elif content_type.startswith("application/json"):
            try:
                await self._validate_json_request(request)
            except HTTPException as e:
                return JSONResponse(
                    status_code=e.status_code,
                    content={"error": e.detail, "type": "validation_error"},
                )

        try:
            response: Response = await call_next(request)
            return response
        except Exception as e:
            logger.error(
                f"Request processing failed: {str(e)}",
                extra={
                    "client_ip": self._get_client_ip(request),
                    "path": request.url.path,
                    "method": request.method,
                },
                exc_info=True,
            )
            raise

    async def _validate_multipart_request(self, request: Request) -> None:
        """Validate multipart form data requests"""
        # This is a basic validation - detailed file validation happens in the endpoint
        # We mainly check for obvious malicious patterns here

        # Check for suspicious file extensions in the path
        suspicious_patterns = [
            ".exe",
            ".bat",
            ".cmd",
            ".scr",
            ".com",
            ".pif",
            ".vbs",
            ".js",
            ".jar",
        ]

        path_lower = request.url.path.lower()
        for pattern in suspicious_patterns:
            if pattern in path_lower:
                logger.warning(
                    f"Suspicious file pattern detected in path: {request.url.path}",
                    extra={
                        "client_ip": self._get_client_ip(request),
                        "path": request.url.path,
                        "pattern": pattern,
                    },
                )
                raise HTTPException(
                    status_code=400,
                    detail="Invalid file type detected in request path",
                )

    async def _validate_json_request(self, request: Request) -> None:
        """Validate JSON request content"""
        try:
            # Read the body to validate JSON structure
            body = await request.body()
            if not body:
                return  # Empty body is fine

            try:
                data = json.loads(body)
                self._check_json_depth(data, current_depth=0)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"Invalid JSON in request: {str(e)}",
                    extra={
                        "client_ip": self._get_client_ip(request),
                        "path": request.url.path,
                    },
                )
                raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")

        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            logger.error(
                f"JSON validation error: {str(e)}",
                extra={
                    "client_ip": self._get_client_ip(request),
                    "path": request.url.path,
                },
                exc_info=True,
            )
            raise HTTPException(status_code=400, detail="Request validation failed")

    def _check_json_depth(self, obj: Any, current_depth: int) -> None:
        """Recursively check JSON nesting depth"""
        if current_depth > self.max_json_depth:
            raise HTTPException(
                status_code=400,
                detail=f"JSON nesting too deep (max depth: {self.max_json_depth})",
            )

        if isinstance(obj, dict):
            for value in obj.values():
                self._check_json_depth(value, current_depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                self._check_json_depth(item, current_depth + 1)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host

        return "unknown"


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware for handling request timeouts"""

    def __init__(self, app: Any, timeout_seconds: float = 30.0):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds
        logger.info(f"Request timeout middleware initialized: {timeout_seconds}s")

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with timeout"""
        import asyncio

        try:
            # Create timeout for the request
            response: Response = await asyncio.wait_for(
                call_next(request), timeout=self.timeout_seconds
            )
            return response

        except asyncio.TimeoutError:
            logger.warning(
                f"Request timeout after {self.timeout_seconds}s",
                extra={
                    "client_ip": self._get_client_ip(request),
                    "path": request.url.path,
                    "method": request.method,
                    "timeout": self.timeout_seconds,
                },
            )
            return JSONResponse(
                status_code=408,
                content={
                    "error": "Request timeout",
                    "message": f"Request took longer than {self.timeout_seconds} seconds",
                    "timeout_seconds": self.timeout_seconds,
                },
            )

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host

        return "unknown"
