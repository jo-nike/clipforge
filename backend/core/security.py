"""
Security utilities for ClipForge
Handles path validation, input sanitization, and security checks
"""

import hashlib
import hmac
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import bleach  # type: ignore[import-untyped]
from core.logging import get_logger

logger = get_logger("security")


class SecurityUtils:
    """Utility class for security-related operations"""

    @staticmethod
    def validate_file_path(file_path: Union[str, Path], base_path: Union[str, Path]) -> Path:
        """
        Validate file path to prevent directory traversal attacks

        Args:
            file_path: The file path to validate
            base_path: The base directory that files must be within

        Returns:
            Resolved Path object if valid

        Raises:
            ValueError: If path is invalid or outside base directory
        """
        try:
            # Convert to Path objects and resolve
            file_path = Path(file_path).resolve()
            base_path = Path(base_path).resolve()

            # Check if file path is within base directory
            if not str(file_path).startswith(str(base_path)):
                raise ValueError(f"Access denied - path outside allowed directory: {file_path}")

            return file_path

        except (OSError, ValueError) as e:
            raise ValueError(f"Invalid file path: {e}")

    @staticmethod
    def sanitize_filename(filename: str, max_length: int = 255) -> str:
        """
        Sanitize filename to prevent security issues

        Args:
            filename: Original filename
            max_length: Maximum allowed filename length

        Returns:
            Sanitized filename
        """
        if not filename:
            raise ValueError("Filename cannot be empty")

        # Remove or replace dangerous characters
        # Keep alphanumeric, dots, dashes, underscores
        sanitized = re.sub(r"[^\w\-_\.]", "_", filename)

        # Remove multiple consecutive dots/underscores
        sanitized = re.sub(r"[._]{2,}", "_", sanitized)

        # Remove leading/trailing dots and underscores
        sanitized = sanitized.strip("._")

        if not sanitized:
            raise ValueError("Filename becomes empty after sanitization")

        # Truncate if too long
        if len(sanitized) > max_length:
            name, ext = sanitized.rsplit(".", 1) if "." in sanitized else (sanitized, "")
            max_name_length = max_length - len(ext) - 1 if ext else max_length
            sanitized = name[:max_name_length] + ("." + ext if ext else "")

        return sanitized

    @staticmethod
    def generate_file_signature(file_id: str, user_id: str, secret_key: str) -> str:
        """
        Generate HMAC signature for secure file access

        Args:
            file_id: Unique file identifier
            user_id: User identifier
            secret_key: Secret key for HMAC

        Returns:
            HMAC signature as hex string
        """
        message = f"{file_id}:{user_id}".encode("utf-8")
        return hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()

    @staticmethod
    def verify_file_signature(file_id: str, user_id: str, signature: str, secret_key: str) -> bool:
        """
        Verify HMAC signature for file access

        Args:
            file_id: Unique file identifier
            user_id: User identifier
            signature: Provided signature to verify
            secret_key: Secret key for HMAC

        Returns:
            True if signature is valid, False otherwise
        """
        expected_signature = SecurityUtils.generate_file_signature(file_id, user_id, secret_key)
        return hmac.compare_digest(signature, expected_signature)

    @staticmethod
    def validate_time_format(time_str: str) -> bool:
        """
        Validate time format (HH:MM:SS or MM:SS)

        Args:
            time_str: Time string to validate

        Returns:
            True if valid format, False otherwise
        """
        if not time_str:
            return False

        # Pattern for HH:MM:SS or MM:SS
        pattern = r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})(?:\.(\d+))?$"
        match = re.match(pattern, time_str)

        if not match:
            return False

        # Extract components
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2))
        seconds = int(match.group(3))

        # Validate ranges
        return 0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59

    @staticmethod
    def sanitize_user_input(input_str: str, max_length: int = 1000) -> str:
        """
        Sanitize user input to prevent XSS and other attacks

        Args:
            input_str: User input string
            max_length: Maximum allowed length

        Returns:
            Sanitized string
        """
        if not input_str:
            return ""

        # Remove null bytes and control characters
        sanitized = "".join(char for char in input_str if ord(char) >= 32 or char in "\t\n\r")

        # Truncate if too long
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        # Strip whitespace
        return sanitized.strip()

    @staticmethod
    def validate_clip_duration(
        start_time: str, end_time: str, max_duration: Optional[int] = None
    ) -> bool:
        """
        Validate clip duration doesn't exceed limits

        Args:
            start_time: Start time string
            end_time: End time string
            max_duration: Maximum duration in seconds (uses settings.max_clip_duration if None)

        Returns:
            True if duration is valid, False otherwise
        """
        from services.clip_service import TimeUtils

        from .config import settings

        if max_duration is None:
            max_duration = settings.max_clip_duration

        try:
            start_seconds = TimeUtils.parse_time_to_seconds(start_time)
            end_seconds = TimeUtils.parse_time_to_seconds(end_time)

            if end_seconds <= start_seconds:
                return False

            duration = end_seconds - start_seconds
            return duration <= max_duration

        except (ValueError, AttributeError):
            return False

    @staticmethod
    def is_safe_redirect_url(url: str, allowed_hosts: Optional[list] = None) -> bool:
        """
        Check if redirect URL is safe (prevent open redirect attacks)

        Args:
            url: URL to validate
            allowed_hosts: List of allowed host names

        Returns:
            True if URL is safe for redirect, False otherwise
        """
        if not url:
            return False

        # Block obvious dangerous schemes
        dangerous_schemes = ["javascript:", "data:", "vbscript:"]
        for scheme in dangerous_schemes:
            if url.lower().startswith(scheme):
                return False

        # For relative URLs, they're generally safe
        if url.startswith("/") and not url.startswith("//"):
            return True

        # For absolute URLs, check allowed hosts if provided
        if allowed_hosts and url.startswith(("http://", "https://")):
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return parsed.hostname in allowed_hosts

        # Default to blocking absolute URLs without explicit allow list
        return not url.startswith(("http://", "https://"))

    @staticmethod
    def validate_file_extension(filename: str, allowed_extensions: List[str]) -> bool:
        """
        Validate file extension against allowed list

        Args:
            filename: The filename to check
            allowed_extensions: List of allowed extensions (with or without dots)

        Returns:
            True if extension is allowed, False otherwise
        """
        if not filename or "." not in filename:
            return False

        file_ext = filename.rsplit(".", 1)[1].lower()
        normalized_extensions = [ext.lstrip(".").lower() for ext in allowed_extensions]

        return file_ext in normalized_extensions

    @staticmethod
    def prevent_path_traversal(file_path: str) -> str:
        """
        Enhanced path traversal prevention

        Args:
            file_path: The file path to sanitize

        Returns:
            Sanitized path

        Raises:
            ValueError: If path contains traversal attempts
        """
        if not file_path:
            raise ValueError("File path cannot be empty")

        # Normalize path separators
        normalized = file_path.replace("\\", "/").replace("//", "/")

        # Check for obvious traversal patterns
        dangerous_patterns = [
            "../",
            "..\\",
            "..%2f",
            "..%2F",
            "..%5c",
            "..%5C",
            "%2e%2e%2f",
            "%2e%2e%5c",
            "....%2f",
            "....%5c",
            "..%252f",
            "..%252F",
            "%252e%252e%252f",
        ]

        for pattern in dangerous_patterns:
            if pattern in normalized.lower():
                logger.warning(f"Path traversal attempt detected: {file_path}")
                raise ValueError("Path traversal attempt detected")

        # Remove any remaining traversal components
        parts = normalized.split("/")
        clean_parts: List[str] = []

        for part in parts:
            if part == "." or part == "":
                continue
            elif part == "..":
                if clean_parts:
                    clean_parts.pop()
            else:
                clean_parts.append(part)

        return "/".join(clean_parts)

    @staticmethod
    def sanitize_html_input(html_input: str, allowed_tags: Optional[List[str]] = None) -> str:
        """
        Sanitize HTML input to prevent XSS attacks

        Args:
            html_input: HTML string to sanitize
            allowed_tags: List of allowed HTML tags (default: very restrictive)

        Returns:
            Sanitized HTML string
        """
        if not html_input:
            return ""

        if allowed_tags is None:
            # Very restrictive - only basic formatting
            allowed_tags = ["b", "i", "em", "strong", "p", "br"]

        # Use bleach to sanitize HTML
        allowed_attributes: Dict[str, List[str]] = {
            # No attributes allowed for maximum security
        }

        sanitized = bleach.clean(
            html_input, tags=allowed_tags, attributes=allowed_attributes, strip=True
        )

        return str(sanitized)

    @staticmethod
    def validate_ip_address(ip_address: str) -> bool:
        """
        Validate IP address format

        Args:
            ip_address: IP address string to validate

        Returns:
            True if valid IP address, False otherwise
        """
        import ipaddress

        try:
            ipaddress.ip_address(ip_address)
            return True
        except ValueError:
            return False

    @staticmethod
    def is_private_ip(ip_address: str) -> bool:
        """
        Check if IP address is private/internal

        Args:
            ip_address: IP address string

        Returns:
            True if private IP, False otherwise
        """
        import ipaddress

        try:
            ip = ipaddress.ip_address(ip_address)
            return ip.is_private
        except ValueError:
            return False

    @staticmethod
    def generate_csrf_token() -> str:
        """
        Generate a CSRF token

        Returns:
            CSRF token as hex string
        """
        import secrets

        return secrets.token_hex(32)

    @staticmethod
    def constant_time_compare(a: str, b: str) -> bool:
        """
        Constant-time string comparison to prevent timing attacks

        Args:
            a: First string
            b: Second string

        Returns:
            True if strings are equal, False otherwise
        """
        return hmac.compare_digest(a, b)

    @staticmethod
    def rate_limit_key(identifier: str, action: str, window: str = "1h") -> str:
        """
        Generate rate limiting key

        Args:
            identifier: User/IP identifier
            action: Action being performed
            window: Time window for rate limiting

        Returns:
            Rate limit key string
        """
        return f"rate_limit:{action}:{identifier}:{window}"

    @staticmethod
    def validate_content_type(content_type: str, allowed_types: List[str]) -> bool:
        """
        Validate content type against allowed list

        Args:
            content_type: Content type to validate
            allowed_types: List of allowed content types

        Returns:
            True if content type is allowed, False otherwise
        """
        if not content_type:
            return False

        # Extract main content type (ignore charset, boundary, etc.)
        main_type = content_type.split(";")[0].strip().lower()
        normalized_allowed = [ct.strip().lower() for ct in allowed_types]

        return main_type in normalized_allowed

    @staticmethod
    def sanitize_log_data(data: str) -> str:
        """
        Sanitize data before logging to prevent log injection

        Args:
            data: Data to sanitize

        Returns:
            Sanitized data safe for logging
        """
        if not data:
            return ""

        # Remove control characters except tab, newline, carriage return
        sanitized = "".join(char for char in data if ord(char) >= 32 or char in "\t\n\r")

        # Replace common injection patterns
        sanitized = sanitized.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

        # Truncate if too long
        if len(sanitized) > 1000:
            sanitized = sanitized[:997] + "..."

        return sanitized


class InputValidator:
    """Validator class for API inputs"""

    @staticmethod
    def validate_pagination(page: int, page_size: int, max_page_size: int = 100) -> Tuple[int, int]:
        """
        Validate and normalize pagination parameters

        Args:
            page: Page number
            page_size: Items per page
            max_page_size: Maximum allowed page size

        Returns:
            Tuple of (validated_page, validated_page_size)
        """
        # Normalize page
        if page < 1:
            page = 1

        # Normalize page size
        if page_size < 1:
            page_size = 20
        elif page_size > max_page_size:
            page_size = max_page_size

        return page, page_size

    @staticmethod
    def validate_quality_setting(quality: str) -> str:
        """
        Validate video quality setting

        Args:
            quality: Quality setting string

        Returns:
            Validated quality setting

        Raises:
            ValueError: If quality is invalid
        """
        allowed_qualities = ["low", "medium", "high", "original"]

        if quality not in allowed_qualities:
            raise ValueError(f"Invalid quality. Must be one of: {', '.join(allowed_qualities)}")

        return quality

    @staticmethod
    def validate_format_setting(format_type: str) -> str:
        """
        Validate output format setting

        Args:
            format_type: Format setting string

        Returns:
            Validated format setting

        Raises:
            ValueError: If format is invalid
        """
        allowed_formats = ["mp4", "webm", "mov"]

        if format_type not in allowed_formats:
            raise ValueError(f"Invalid format. Must be one of: {', '.join(allowed_formats)}")

        return format_type
