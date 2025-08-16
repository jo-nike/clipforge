"""
Structured Logging Configuration for ClipForge
Provides consistent logging format with correlation IDs and security events
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

from core.config import settings

# Context variable for request correlation ID
correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if available
        current_correlation_id = correlation_id.get()
        if current_correlation_id:
            log_entry["correlation_id"] = current_correlation_id

        # Add extra fields if present
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id

        if hasattr(record, "endpoint"):
            log_entry["endpoint"] = record.endpoint

        if hasattr(record, "method"):
            log_entry["method"] = record.method

        if hasattr(record, "status_code"):
            log_entry["status_code"] = record.status_code

        if hasattr(record, "duration"):
            log_entry["duration_ms"] = record.duration

        if hasattr(record, "security_event"):
            log_entry["security_event"] = record.security_event

        if hasattr(record, "error_details"):
            log_entry["error_details"] = record.error_details

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry)


class SecurityLogger:
    """Specialized logger for security events"""

    def __init__(self) -> None:
        self.logger = logging.getLogger("clipforge.security")

    def log_authentication_attempt(self, username: str, success: bool, ip_address: str) -> None:
        """Log authentication attempts"""
        self.logger.info(
            f"Authentication {'successful' if success else 'failed'} for user {username}",
            extra={
                "security_event": "authentication",
                "username": username,
                "success": success,
                "ip_address": ip_address,
            },
        )

    def log_authorization_failure(self, user_id: str, resource: str, action: str) -> None:
        """Log authorization failures"""
        self.logger.warning(
            f"Authorization failed for user {user_id} accessing {resource} with action {action}",
            extra={
                "security_event": "authorization_failure",
                "user_id": user_id,
                "resource": resource,
                "action": action,
            },
        )

    def log_rate_limit_exceeded(self, ip_address: str, endpoint: str) -> None:
        """Log rate limit violations"""
        self.logger.warning(
            f"Rate limit exceeded from {ip_address} for endpoint {endpoint}",
            extra={
                "security_event": "rate_limit_exceeded",
                "ip_address": ip_address,
                "endpoint": endpoint,
            },
        )

    def log_suspicious_activity(self, user_id: str, activity: str, details: Dict[str, Any]) -> None:
        """Log suspicious activities"""
        self.logger.warning(
            f"Suspicious activity detected for user {user_id}: {activity}",
            extra={
                "security_event": "suspicious_activity",
                "user_id": user_id,
                "activity": activity,
                "details": details,
            },
        )

    def log_file_access_attempt(self, user_id: str, file_path: str, success: bool) -> None:
        """Log file access attempts"""
        self.logger.info(
            f"File access {'successful' if success else 'failed'} for user {user_id}: {file_path}",
            extra={
                "security_event": "file_access",
                "user_id": user_id,
                "file_path": file_path,
                "success": success,
            },
        )


class PerformanceLogger:
    """Specialized logger for performance monitoring"""

    def __init__(self) -> None:
        self.logger = logging.getLogger("clipforge.performance")

    def log_request_duration(
        self, endpoint: str, method: str, duration_ms: float, status_code: int
    ) -> None:
        """Log API request performance"""
        self.logger.info(
            f"{method} {endpoint} completed in {duration_ms:.2f}ms with status {status_code}",
            extra={
                "endpoint": endpoint,
                "method": method,
                "duration": duration_ms,
                "status_code": status_code,
            },
        )

    def log_database_query_duration(self, query_type: str, duration_ms: float) -> None:
        """Log database query performance"""
        self.logger.info(
            f"Database {query_type} completed in {duration_ms:.2f}ms",
            extra={"query_type": query_type, "duration": duration_ms},
        )

    def log_media_processing_duration(
        self, operation: str, file_size_mb: float, duration_ms: float
    ) -> None:
        """Log media processing performance"""
        self.logger.info(
            f"Media {operation} ({file_size_mb:.2f}MB) completed in {duration_ms:.2f}ms",
            extra={
                "operation": operation,
                "file_size_mb": file_size_mb,
                "duration": duration_ms,
            },
        )


def setup_logging() -> None:
    """Configure structured logging for the application"""

    # Create formatters
    if settings.debug:
        # Use simple format for development
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    else:
        # Use structured JSON format for production
        formatter = StructuredFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Configure specific loggers
    loggers_config = {
        "clipforge": settings.log_level,
        "clipforge.security": "INFO",
        "clipforge.performance": "INFO",
        "uvicorn.access": "INFO" if settings.debug else "WARNING",
        "uvicorn.error": "INFO",
        "sqlalchemy.engine": "WARNING",  # Suppress SQL query logging
        "sqlalchemy.dialects": "WARNING",  # Suppress SQL dialect logging
        "sqlalchemy.pool": "WARNING",  # Suppress connection pool logging
        "sqlalchemy.orm": "WARNING",  # Suppress ORM logging
    }

    for logger_name, level in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level))
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance"""
    return logging.getLogger(f"clipforge.{name}")


def set_correlation_id(request_id: Optional[str] = None) -> str:
    """Set correlation ID for request tracking"""
    if request_id is None:
        request_id = str(uuid.uuid4())
    correlation_id.set(request_id)
    return request_id


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID"""
    return correlation_id.get()


# Initialize specialized loggers
security_logger = SecurityLogger()
performance_logger = PerformanceLogger()

# Export commonly used functions
__all__ = [
    "setup_logging",
    "get_logger",
    "set_correlation_id",
    "get_correlation_id",
    "security_logger",
    "performance_logger",
]
