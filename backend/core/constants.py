"""
Application constants for ClipForge
Contains default values that can be overridden by environment variables
"""

# Application Info
APP_NAME = "ClipForge"
APP_VERSION = "1.0.0"

# JWT Settings (algorithms and structure, not secrets)
JWT_ALGORITHM = "HS256"
DEFAULT_JWT_EXPIRY_HOURS = 1
DEFAULT_JWT_REMEMBER_DAYS = 30

# Database Defaults
DEFAULT_DATABASE_URL = "sqlite:///static/db/database.db"
DEFAULT_DATABASE_POOL_SIZE = 5

# CORS Defaults
DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"]

# Storage Defaults
DEFAULT_CLIPS_STORAGE_PATH = "static/clips"
DEFAULT_CLIP_RETENTION_DAYS = 7
DEFAULT_MAX_CLIP_DURATION = 600  # 10 minutes
DEFAULT_MAX_CLIP_SIZE_MB = 500

# Rate Limiting Defaults
DEFAULT_RATE_LIMIT_REQUESTS = 100
DEFAULT_RATE_LIMIT_WINDOW = 3  # seconds

# Server Defaults
DEFAULT_HOST = "0.0.0.0"  # nosec B104 - intentional bind to all interfaces for web server
DEFAULT_PORT = 8002
DEFAULT_SECURE_COOKIES = False  # Set to True in production with HTTPS

# Timeout Defaults
DEFAULT_PLEX_TIMEOUT = 30.0

# User Limits Defaults
DEFAULT_USER_VIDEO_LIMIT = 60

# Debug & Test Defaults
DEFAULT_DEBUG = False
DEFAULT_TEST_MODE = False
DEFAULT_TEST_VIDEO_FILE = "test.mkv"
