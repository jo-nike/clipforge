"""
Hybrid CSRF Protection Middleware for ClipForge
Provides CSRF protection using double-submit cookie pattern with API bypass
Supports both browser-based requests and API access via tokens
"""

import logging
import secrets
from typing import Any, Dict, Optional, Set

from core.config import settings
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Hybrid CSRF protection middleware using double-submit cookie pattern"""

    def __init__(self, app: Any, exempt_path_patterns: Optional[Set[str]] = None):
        super().__init__(app)

        # Path patterns that don't require CSRF protection
        self.exempt_patterns = exempt_path_patterns or {
            "/api/health",
            "/api/v1/health",
            "/api/v1/metrics",
            "/api/v1/auth/pin",  # Plex OAuth PIN creation
            "/api/v1/auth/pin/",  # Plex OAuth PIN checking (prefix match)
            "/api/v1/auth/signin",  # Initial login
        }

        # Methods that require CSRF protection
        self.protected_methods = {"POST", "PUT", "DELETE", "PATCH"}

        # CSRF cookie settings
        self.csrf_cookie_name = "csrf_token"
        self.csrf_header_name = "X-CSRF-Token"

        logger.info(f"Hybrid CSRF protection initialized, exempt patterns: {self.exempt_patterns}")

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with hybrid CSRF protection"""

        # Skip CSRF protection for safe methods
        if request.method not in self.protected_methods:
            response: Response = await call_next(request)
            self._set_csrf_cookie(response)
            return response

        # Skip CSRF protection for browser extensions
        origin = request.headers.get("origin", "")
        if origin.startswith("chrome-extension://") or origin.startswith("moz-extension://"):
            logger.info(f"CSRF exempt for browser extension: {origin}")
            extension_response: Response = await call_next(request)
            self._set_csrf_cookie(extension_response)
            return extension_response

        # Skip CSRF protection for exempt path patterns
        request_path = request.url.path
        logger.debug(f"Checking CSRF exemption for path: {request_path}")
        
        if self._is_exempt_path(request_path):
            logger.info(f"CSRF exempt path: {request_path}")
            exempt_response: Response = await call_next(request)
            self._set_csrf_cookie(exempt_response)
            return exempt_response

        # Skip CSRF protection for API authentication
        if self._has_api_authentication(request):
            logger.debug(
                f"Skipping CSRF for API authenticated request: {request.url.path}",
                extra={"client_ip": self._get_client_ip(request)},
            )
            api_response: Response = await call_next(request)
            self._set_csrf_cookie(api_response)
            return api_response

        # Validate CSRF token for browser-based requests
        try:
            self._validate_csrf_token(request)
        except HTTPException as e:
            logger.warning(
                f"CSRF validation failed: {e.detail}",
                extra={
                    "client_ip": self._get_client_ip(request),
                    "path": request.url.path,
                    "method": request.method,
                    "user_agent": request.headers.get("user-agent", "unknown"),
                },
            )
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": "CSRF protection failed",
                    "message": e.detail,
                    "type": "csrf_error",
                },
            )

        # Process the request
        validated_response: Response = await call_next(request)

        # Set/refresh CSRF cookie on successful requests
        if 200 <= validated_response.status_code < 300:
            self._set_csrf_cookie(validated_response)

        return validated_response

    def _is_exempt_path(self, path: str) -> bool:
        """Check if path matches any exempt pattern"""
        for pattern in self.exempt_patterns:
            if pattern.endswith("/"):
                # Prefix match for patterns ending with /
                if path.startswith(pattern):
                    return True
            else:
                # Exact match for specific paths
                if path == pattern:
                    return True
        return False

    def _has_api_authentication(self, request: Request) -> bool:
        """Check if request has API authentication (API key or Bearer token)"""
        # Check for API key
        api_key = request.headers.get("X-API-Key")
        if api_key and len(api_key) >= 32:  # Valid API key format
            return True

        # Check for Bearer token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and len(auth_header) > 7:
            return True

        return False

    def _validate_csrf_token(self, request: Request) -> None:
        """Validate CSRF token using double-submit cookie pattern"""

        # Get token from header
        header_token = request.headers.get(self.csrf_header_name)

        if not header_token:
            # Try to get from form data for multipart requests
            if request.headers.get("content-type", "").startswith("multipart/form-data"):
                try:
                    # Note: We can't await here, so this is best effort
                    # Main protection comes from header token
                    pass
                except Exception:
                    pass

        if not header_token:
            raise HTTPException(status_code=403, detail="CSRF token missing from request headers")

        # Get token from cookie
        cookie_token = request.cookies.get(self.csrf_cookie_name)

        if not cookie_token:
            raise HTTPException(
                status_code=403, detail="CSRF cookie missing - please refresh the page"
            )

        # Validate tokens match (double-submit pattern)
        if not secrets.compare_digest(header_token, cookie_token):
            raise HTTPException(status_code=403, detail="CSRF token mismatch")

    def _generate_token(self) -> str:
        """Generate a new CSRF token"""
        return secrets.token_urlsafe(32)

    def _set_csrf_cookie(self, response: Response) -> None:
        """Set CSRF token in cookie that JavaScript can read"""
        # Generate new token for each response (token rotation)
        csrf_token = self._generate_token()

        # Set cookie that JavaScript can read (not httpOnly)
        response.set_cookie(
            key=self.csrf_cookie_name,
            value=csrf_token,
            max_age=3600,  # 1 hour
            secure=settings.secure_cookies,  # HTTPS only in production
            samesite="strict",  # CSRF protection
            httponly=False,  # Allow JavaScript access
        )

        # Also set in header for immediate use
        response.headers[self.csrf_header_name] = csrf_token

        logger.debug(f"Set CSRF token: {csrf_token[:8]}...")

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


class APIKeyMiddleware(BaseHTTPMiddleware):
    """API key authentication middleware as alternative to JWT"""

    def __init__(self, app: Any, api_key_header: str = "X-API-Key"):
        super().__init__(app)
        self.api_key_header = api_key_header

        # Paths that support API key authentication
        self.api_key_paths = {
            "/api/v1/auth",     # Allow API key for auth endpoints
            "/api/v1/clips",
            "/api/v1/sessions",
            "/api/v1/storage",
            "/api/v1/users",    # Allow API key for user endpoints
        }

        logger.info(f"API key middleware initialized for header: {api_key_header}")

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process request with API key support"""

        # Check if this path supports API key auth
        path_supports_api_key = any(
            request.url.path.startswith(path) for path in self.api_key_paths
        )

        if not path_supports_api_key:
            non_api_response: Response = await call_next(request)
            return non_api_response

        # Check for API key in headers
        api_key = request.headers.get(self.api_key_header)

        if api_key:
            # Validate API key and set user context
            try:
                user_context = await self._validate_api_key(api_key)
                if user_context:
                    # Add user info to request state for downstream handlers
                    request.state.api_key_user = user_context

                    logger.info(
                        "API key authentication successful",
                        extra={
                            "user_id": user_context.get("user_id"),
                            "client_ip": self._get_client_ip(request),
                            "path": request.url.path,
                        },
                    )
            except Exception as e:
                logger.warning(
                    f"API key validation failed: {str(e)}",
                    extra={
                        "client_ip": self._get_client_ip(request),
                        "path": request.url.path,
                    },
                )
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "Invalid API key",
                        "message": "The provided API key is invalid or expired",
                    },
                )

        final_response: Response = await call_next(request)
        return final_response

    async def _validate_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Validate API key and return user context"""
        from core.constants import DEFAULT_API_KEY
        
        if not api_key or len(api_key) < 32:
            return None

        # Check against the configured API key
        # In production, this should check against a database of user API keys
        if api_key != DEFAULT_API_KEY:
            logger.warning(f"Invalid API key attempted: {api_key[:8]}...")
            return None

        # Return user context for valid API key
        return {
            "user_id": "api_user",
            "username": "API User",
            "auth_method": "api_key",
            "permissions": ["read", "write"],
        }

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
