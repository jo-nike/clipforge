"""
Audit logging system for ClipForge security and compliance
Tracks sensitive operations and user activities for security monitoring
"""

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from core.logging import get_logger


class AuditEventType(Enum):
    """Types of auditable events"""

    # Authentication events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    AUTH_LOGOUT = "auth_logout"

    # Resource access
    CLIP_CREATE = "clip_create"
    CLIP_DELETE = "clip_delete"
    CLIP_EDIT = "clip_edit"
    CLIP_ACCESS = "clip_access"
    CLIP_BULK_DELETE = "clip_bulk_delete"

    # File operations
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_DELETE = "file_delete"

    # Administrative actions
    USER_CREATE = "user_create"
    USER_DELETE = "user_delete"
    USER_MODIFY = "user_modify"

    # Security events
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    INPUT_VALIDATION_FAILED = "input_validation_failed"

    # System events
    SYSTEM_ERROR = "system_error"
    CONFIGURATION_CHANGE = "configuration_change"


class AuditSeverity(Enum):
    """Audit event severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditEvent:
    """Represents a single audit event"""

    def __init__(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        outcome: str = "success",
        severity: AuditSeverity = AuditSeverity.LOW,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        self.event_id = str(uuid.uuid4())
        self.timestamp = datetime.utcnow()
        self.event_type = event_type
        self.user_id = user_id
        self.username = username
        self.resource_id = resource_id
        self.resource_type = resource_type
        self.action = action
        self.outcome = outcome
        self.severity = severity
        self.details = details or {}
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.correlation_id = correlation_id

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit event to dictionary for logging"""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "username": self.username,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "action": self.action,
            "outcome": self.outcome,
            "severity": self.severity.value,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "correlation_id": self.correlation_id,
        }

    def to_json(self) -> str:
        """Convert audit event to JSON string"""
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """Main audit logging class"""

    def __init__(self) -> None:
        self.logger = get_logger("audit")
        self.structured_logger = structlog.get_logger("audit")

    def log_event(self, event: AuditEvent) -> None:
        """Log an audit event"""
        event_data = event.to_dict()

        # Log with appropriate level based on severity
        if event.severity == AuditSeverity.CRITICAL:
            self.logger.critical(f"AUDIT: {event.event_type.value}", extra=event_data)
        elif event.severity == AuditSeverity.HIGH:
            self.logger.error(f"AUDIT: {event.event_type.value}", extra=event_data)
        elif event.severity == AuditSeverity.MEDIUM:
            self.logger.warning(f"AUDIT: {event.event_type.value}", extra=event_data)
        else:
            self.logger.info(f"AUDIT: {event.event_type.value}", extra=event_data)

        # Also log to structured logger for better parsing
        self.structured_logger.info(
            "audit_event",
            **event_data,
        )

    def log_auth_success(
        self,
        user_id: str,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log successful authentication"""
        event = AuditEvent(
            event_type=AuditEventType.AUTH_SUCCESS,
            user_id=user_id,
            username=username,
            action="login",
            outcome="success",
            severity=AuditSeverity.LOW,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        self.log_event(event)

    def log_auth_failure(
        self,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log failed authentication attempt"""
        event = AuditEvent(
            event_type=AuditEventType.AUTH_FAILURE,
            username=username,
            action="login",
            outcome="failure",
            severity=AuditSeverity.MEDIUM,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        self.log_event(event)

    def log_resource_access(
        self,
        event_type: AuditEventType,
        user_id: str,
        username: str,
        resource_id: str,
        resource_type: str,
        action: str,
        outcome: str = "success",
        severity: AuditSeverity = AuditSeverity.LOW,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log resource access events (create, read, update, delete)"""
        event = AuditEvent(
            event_type=event_type,
            user_id=user_id,
            username=username,
            resource_id=resource_id,
            resource_type=resource_type,
            action=action,
            outcome=outcome,
            severity=severity,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        self.log_event(event)

    def log_clip_create(
        self,
        user_id: str,
        username: str,
        clip_id: str,
        ip_address: Optional[str] = None,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log clip creation"""
        self.log_resource_access(
            event_type=AuditEventType.CLIP_CREATE,
            user_id=user_id,
            username=username,
            resource_id=clip_id,
            resource_type="clip",
            action="create",
            severity=AuditSeverity.LOW,
            ip_address=ip_address,
            correlation_id=correlation_id,
            details=details,
        )

    def log_clip_delete(
        self,
        user_id: str,
        username: str,
        clip_id: str,
        ip_address: Optional[str] = None,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log clip deletion"""
        self.log_resource_access(
            event_type=AuditEventType.CLIP_DELETE,
            user_id=user_id,
            username=username,
            resource_id=clip_id,
            resource_type="clip",
            action="delete",
            severity=AuditSeverity.MEDIUM,
            ip_address=ip_address,
            correlation_id=correlation_id,
            details=details,
        )

    def log_clip_bulk_delete(
        self,
        user_id: str,
        username: str,
        clip_ids: List[str],
        deleted_count: int,
        failed_count: int,
        ip_address: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Log bulk clip deletion"""
        details = {
            "clip_ids": clip_ids,
            "total_requested": len(clip_ids),
            "deleted_count": deleted_count,
            "failed_count": failed_count,
        }

        self.log_resource_access(
            event_type=AuditEventType.CLIP_BULK_DELETE,
            user_id=user_id,
            username=username,
            resource_id=f"bulk_{len(clip_ids)}_clips",
            resource_type="clip",
            action="bulk_delete",
            severity=AuditSeverity.MEDIUM if deleted_count > 5 else AuditSeverity.LOW,
            ip_address=ip_address,
            correlation_id=correlation_id,
            details=details,
        )

    def log_security_violation(
        self,
        violation_type: str,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log security violations"""
        violation_details = {"violation_type": violation_type}
        if details:
            violation_details.update(details)

        event = AuditEvent(
            event_type=AuditEventType.SECURITY_VIOLATION,
            user_id=user_id,
            username=username,
            action=violation_type,
            outcome="blocked",
            severity=AuditSeverity.HIGH,
            details=violation_details,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        self.log_event(event)

    def log_unauthorized_access(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log unauthorized access attempts"""
        event = AuditEvent(
            event_type=AuditEventType.UNAUTHORIZED_ACCESS,
            user_id=user_id,
            username=username,
            resource_id=resource_id,
            resource_type=resource_type,
            action="access_denied",
            outcome="blocked",
            severity=AuditSeverity.HIGH,
            details=details,
            ip_address=ip_address,
            correlation_id=correlation_id,
        )
        self.log_event(event)

    def log_input_validation_failure(
        self,
        field_name: str,
        field_value: Optional[str] = None,
        validation_error: str = "",
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Log input validation failures"""
        details = {"field_name": field_name, "validation_error": validation_error}

        # Don't log sensitive field values
        if (
            field_name.lower() not in ["password", "token", "secret", "key"]
            and field_value is not None
        ):
            details["field_value"] = field_value

        event = AuditEvent(
            event_type=AuditEventType.INPUT_VALIDATION_FAILED,
            user_id=user_id,
            username=username,
            action="input_validation",
            outcome="blocked",
            severity=AuditSeverity.MEDIUM,
            details=details,
            ip_address=ip_address,
            correlation_id=correlation_id,
        )
        self.log_event(event)


# Global audit logger instance
audit_logger = AuditLogger()


# Convenience functions for common audit operations
def log_auth_success(user_id: str, username: str, **kwargs: Any) -> None:
    """Convenience function for logging successful authentication"""
    audit_logger.log_auth_success(user_id, username, **kwargs)


def log_auth_failure(username: Optional[str] = None, **kwargs: Any) -> None:
    """Convenience function for logging failed authentication"""
    audit_logger.log_auth_failure(username, **kwargs)


def log_clip_create(user_id: str, username: str, clip_id: str, **kwargs: Any) -> None:
    """Convenience function for logging clip creation"""
    audit_logger.log_clip_create(user_id, username, clip_id, **kwargs)


def log_clip_delete(user_id: str, username: str, clip_id: str, **kwargs: Any) -> None:
    """Convenience function for logging clip deletion"""
    audit_logger.log_clip_delete(user_id, username, clip_id, **kwargs)


def log_clip_bulk_delete(
    user_id: str,
    username: str,
    clip_ids: list,
    deleted_count: int,
    failed_count: int,
    **kwargs: Any,
) -> None:
    """Convenience function for logging bulk clip deletion"""
    audit_logger.log_clip_bulk_delete(
        user_id, username, clip_ids, deleted_count, failed_count, **kwargs
    )


def log_security_violation(violation_type: str, **kwargs: Any) -> None:
    """Convenience function for logging security violations"""
    audit_logger.log_security_violation(violation_type, **kwargs)


def log_unauthorized_access(resource_type: str, **kwargs: Any) -> None:
    """Convenience function for logging unauthorized access"""
    audit_logger.log_unauthorized_access(resource_type, **kwargs)


def log_input_validation_failure(field_name: str, **kwargs: Any) -> None:
    """Convenience function for logging input validation failures"""
    audit_logger.log_input_validation_failure(field_name, **kwargs)
