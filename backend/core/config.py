"""
Secure configuration management for ClipForge
Replaces hardcoded configurations with environment-based settings
"""

import os
import secrets
from pathlib import Path
from typing import Any, List, Optional

from pydantic_settings import BaseSettings

from .constants import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_CLIP_RETENTION_DAYS,
    DEFAULT_CLIPS_STORAGE_PATH,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_DATABASE_POOL_SIZE,
    DEFAULT_DATABASE_URL,
    DEFAULT_DEBUG,
    DEFAULT_HOST,
    DEFAULT_JWT_EXPIRY_HOURS,
    DEFAULT_JWT_REMEMBER_DAYS,
    DEFAULT_MAX_CLIP_DURATION,
    DEFAULT_MAX_CLIP_SIZE_MB,
    DEFAULT_PLEX_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_RATE_LIMIT_REQUESTS,
    DEFAULT_RATE_LIMIT_WINDOW,
    DEFAULT_SECURE_COOKIES,
    DEFAULT_TEST_MODE,
    DEFAULT_TEST_VIDEO_FILE,
    DEFAULT_USER_VIDEO_LIMIT,
    JWT_ALGORITHM,
)


class Settings(BaseSettings):
    """Application settings with security validation"""

    # Application
    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    debug: bool = DEFAULT_DEBUG

    # Security
    jwt_secret: str = secrets.token_urlsafe(32)
    jwt_algorithm: str = JWT_ALGORITHM
    jwt_expiry_hours: int = DEFAULT_JWT_EXPIRY_HOURS
    jwt_remember_days: int = DEFAULT_JWT_REMEMBER_DAYS

    # CORS - explicit configuration required
    cors_origins: List[str] = DEFAULT_CORS_ORIGINS

    # Database
    database_url: str = DEFAULT_DATABASE_URL
    database_pool_size: int = DEFAULT_DATABASE_POOL_SIZE

    # Plex
    plex_server_name: Optional[str] = (
        None  # Optional: auto-discovered if plex_server_token is provided
    )
    plex_server_token: Optional[str] = None  # Admin token for the Plex server
    plex_timeout: float = DEFAULT_PLEX_TIMEOUT

    # Storage
    clips_storage_path: str = DEFAULT_CLIPS_STORAGE_PATH
    clip_retention_days: int = DEFAULT_CLIP_RETENTION_DAYS
    max_clip_duration: int = DEFAULT_MAX_CLIP_DURATION
    max_clip_size_mb: int = DEFAULT_MAX_CLIP_SIZE_MB

    # Rate Limiting
    rate_limit_requests: int = DEFAULT_RATE_LIMIT_REQUESTS
    rate_limit_window: int = DEFAULT_RATE_LIMIT_WINDOW

    # Server
    host: str = DEFAULT_HOST  # nosec B104 - intentional bind to all interfaces for web server
    port: int = DEFAULT_PORT

    # Security flags
    secure_cookies: bool = DEFAULT_SECURE_COOKIES  # Set to True in production with HTTPS

    # Test Mode (for development without Plex server)
    test_mode: bool = DEFAULT_TEST_MODE
    test_video_file: str = DEFAULT_TEST_VIDEO_FILE

    # Resilience Settings
    plex_retry_attempts: int = 3
    plex_retry_base_delay: float = 1.0
    plex_retry_max_delay: float = 10.0
    plex_circuit_breaker_failure_threshold: int = 5
    plex_circuit_breaker_recovery_timeout: int = 30

    ffmpeg_retry_attempts: int = 2
    ffmpeg_retry_base_delay: float = 0.5
    ffmpeg_retry_max_delay: float = 5.0
    ffmpeg_circuit_breaker_failure_threshold: int = 3
    ffmpeg_circuit_breaker_recovery_timeout: int = 60

    # Security Settings
    enable_audit_logging: bool = True
    log_level: str = "INFO"  # General logging level
    audit_log_level: str = "INFO"
    max_login_attempts: int = 5
    login_lockout_duration: int = 300  # 5 minutes

    # Performance Settings
    max_concurrent_clips: int = 5
    clip_processing_timeout: int = 300  # 5 minutes

    # User Limits
    user_video_limit: int = DEFAULT_USER_VIDEO_LIMIT

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow overriding with environment variables
        env_prefix = "CLIPFORGE_"

    def validate_settings(self) -> None:
        """Validate critical security settings on startup"""
        errors = []

        # Validate JWT secret
        if self.jwt_secret == "your-secret-key-change-this-in-production":
            errors.append("JWT_SECRET must be changed from default value")

        if len(self.jwt_secret) < 32:
            errors.append("JWT_SECRET must be at least 32 characters long")

        # Validate CORS
        if not self.cors_origins:
            errors.append("CORS_ORIGINS must be configured")

        if "*" in self.cors_origins and not self.debug:
            errors.append("CORS wildcard (*) not allowed in production")

        # Validate storage paths
        if not self.clips_storage_path:
            errors.append("CLIPS_STORAGE_PATH must be configured")

        # Validate rate limiting
        if self.rate_limit_requests <= 0:
            errors.append("RATE_LIMIT_REQUESTS must be positive")

        if self.rate_limit_window <= 0:
            errors.append("RATE_LIMIT_WINDOW must be positive")

        # Validate resilience settings
        if self.plex_retry_attempts < 1:
            errors.append("PLEX_RETRY_ATTEMPTS must be at least 1")

        if self.ffmpeg_retry_attempts < 1:
            errors.append("FFMPEG_RETRY_ATTEMPTS must be at least 1")

        if self.plex_circuit_breaker_failure_threshold < 1:
            errors.append("PLEX_CIRCUIT_BREAKER_FAILURE_THRESHOLD must be at least 1")

        if self.ffmpeg_circuit_breaker_failure_threshold < 1:
            errors.append("FFMPEG_CIRCUIT_BREAKER_FAILURE_THRESHOLD must be at least 1")

        # Validate security settings
        if self.max_login_attempts < 1:
            errors.append("MAX_LOGIN_ATTEMPTS must be at least 1")

        if self.login_lockout_duration < 0:
            errors.append("LOGIN_LOCKOUT_DURATION must be non-negative")

        # Validate performance settings
        if self.max_concurrent_clips < 1:
            errors.append("MAX_CONCURRENT_CLIPS must be at least 1")

        if self.clip_processing_timeout < 10:
            errors.append("CLIP_PROCESSING_TIMEOUT must be at least 10 seconds")

        # Validate user limits
        if self.user_video_limit < 1:
            errors.append("USER_VIDEO_LIMIT must be at least 1")

        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(
                f"- {error}" for error in errors
            )
            raise ValueError(error_msg)

    @property
    def absolute_clips_path(self) -> Path:
        """Get absolute path for clips storage"""
        if os.path.isabs(self.clips_storage_path):
            return Path(self.clips_storage_path)

        # Relative to project root
        project_root = Path(__file__).parent.parent.parent
        return project_root / self.clips_storage_path

    def create_required_directories(self) -> None:
        """Create required storage directories"""
        base_path = self.absolute_clips_path

        # Extract database directory from URL
        if self.database_url.startswith("sqlite:///"):
            db_path = self.database_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                # Relative to project root
                project_root = Path(__file__).parent.parent.parent
                db_path = str(project_root / db_path)
            db_dir = Path(db_path).parent
        else:
            # For non-SQLite databases, create a general db directory
            db_dir = base_path.parent / "db"

        directories = [
            base_path / "videos",
            base_path / "snapshots",
            base_path / "edited",
            db_dir,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization validation and setup"""
        self.validate_settings()
        self.create_required_directories()


# Global settings instance
settings = Settings()
