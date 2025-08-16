"""
Custom Exception Classes for ClipForge
Provides structured error handling with consistent error responses
"""

from typing import Any, Dict, Optional


class ClipForgeException(Exception):
    """Base exception class for ClipForge application"""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}


class AuthenticationError(ClipForgeException):
    """Raised when authentication fails"""

    pass


class AuthorizationError(ClipForgeException):
    """Raised when user lacks permission for requested resource"""

    pass


class ValidationError(ClipForgeException):
    """Raised when input validation fails"""

    pass


class PlexConnectionError(ClipForgeException):
    """Raised when Plex server connection fails"""

    pass


class PlexAuthenticationError(ClipForgeException):
    """Raised when Plex authentication fails"""

    pass


class SessionNotFoundError(ClipForgeException):
    """Raised when requested Plex session is not found"""

    pass


class ClipNotFoundError(ClipForgeException):
    """Raised when requested clip is not found"""

    pass


class ClipProcessingError(ClipForgeException):
    """Raised when clip processing fails"""

    pass


class StorageError(ClipForgeException):
    """Raised when storage operations fail"""

    pass


class StorageLimitExceededError(StorageError):
    """Raised when user storage limit is exceeded"""

    pass


class VideoLimitExceededException(ClipForgeException):
    """Raised when user video limit is exceeded"""

    pass


class FileNotFoundError(ClipForgeException):
    """Raised when requested file is not found"""

    pass


class FileAccessError(ClipForgeException):
    """Raised when file access is denied"""

    pass


class DatabaseError(ClipForgeException):
    """Raised when database operations fail"""

    pass


class ExternalServiceError(ClipForgeException):
    """Raised when external service calls fail"""

    pass


class ConfigurationError(ClipForgeException):
    """Raised when application configuration is invalid"""

    pass


class RateLimitExceededError(ClipForgeException):
    """Raised when rate limit is exceeded"""

    pass


class MediaProcessingError(ClipForgeException):
    """Raised when media processing operations fail"""

    pass


class TemporaryFileError(ClipForgeException):
    """Raised when temporary file operations fail"""

    pass
