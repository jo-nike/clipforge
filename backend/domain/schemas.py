"""
Pydantic schemas for input validation and data serialization
Replaces loose validation with strict type checking and validation
"""

import re
from datetime import datetime
from typing import Dict, List, Optional

from core.security import InputValidator, SecurityUtils
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self


# Authentication Schemas
class SignInRequest(BaseModel):
    """Sign in request with token validation"""

    token: str = Field(..., min_length=1, max_length=500, description="Plex authentication token")
    remember_me: bool = Field(default=False, description="Remember user session")

    @field_validator("token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Token cannot be empty")
        return v.strip()


class SignInResponse(BaseModel):
    """Sign in response"""

    status: str = Field(..., pattern=r"^(success|error)$")
    message: str = Field(..., min_length=1, max_length=200)
    token: Optional[str] = None


# Basic Plex Models (needed as dependencies)
class PlexGuid(BaseModel):
    """Plex GUID model"""

    id: str


class PlexUser(BaseModel):
    """Plex user model"""

    user_id: str
    username: str
    email: str
    thumb: Optional[str] = None
    is_home_user: bool = False
    is_restricted: bool = False


class PlexServerConnection(BaseModel):
    """Plex server connection model"""

    protocol: str
    address: str
    port: int
    uri: str
    local: bool


class PlexServer(BaseModel):
    """Plex server model"""

    name: str
    machine_identifier: str
    host: str
    port: int
    version: str
    scheme: str = "http"
    connections: List[PlexServerConnection] = []
    owned: bool = True
    synced: bool = False
    access_token: Optional[str] = None

    @property
    def url(self) -> str:
        """Get the primary URL for this server"""
        # Prefer local connections first, then remote
        local_connections = [c for c in self.connections if c.local]
        if local_connections:
            conn = local_connections[0]
            return f"{conn.protocol}://{conn.address}:{conn.port}"

        # Fall back to remote connections
        if self.connections:
            conn = self.connections[0]
            return f"{conn.protocol}://{conn.address}:{conn.port}"

        # Last resort: use basic host/port
        return f"{self.scheme}://{self.host}:{self.port}"


class MediaInfo(BaseModel):
    """Media information model"""

    key: str
    rating_key: Optional[str] = None
    guid: Optional[str] = None
    guids: List[PlexGuid] = []
    title: str
    media_type: str
    duration: Optional[int] = None
    thumb: Optional[str] = None
    art: Optional[str] = None
    banner: Optional[str] = None
    theme: Optional[str] = None
    year: Optional[int] = None
    originally_available_at: Optional[str] = None
    added_at: Optional[int] = None
    updated_at: Optional[int] = None
    last_viewed_at: Optional[int] = None
    view_count: Optional[int] = None
    skip_count: Optional[int] = None
    rating: Optional[float] = None
    audience_rating: Optional[float] = None
    content_rating: Optional[str] = None
    studio: Optional[str] = None
    tag_line: Optional[str] = None
    summary: Optional[str] = None

    # TV Show hierarchy
    show_title: Optional[str] = None  # grandparentTitle
    grandparent_key: Optional[str] = None
    grandparent_rating_key: Optional[str] = None
    grandparent_guid: Optional[str] = None
    grandparent_thumb: Optional[str] = None
    grandparent_art: Optional[str] = None
    grandparent_theme: Optional[str] = None

    # Season info
    parent_title: Optional[str] = None  # season title
    parent_key: Optional[str] = None
    parent_rating_key: Optional[str] = None
    parent_guid: Optional[str] = None
    parent_thumb: Optional[str] = None
    parent_art: Optional[str] = None
    parent_theme: Optional[str] = None
    season_number: Optional[int] = None
    parent_index: Optional[int] = None

    # Episode info
    episode_number: Optional[int] = None
    index: Optional[int] = None

    # Media streams containing file paths
    media_streams: List["PlexStreamMedia"] = []


class PlayerInfo(BaseModel):
    """Player information model"""

    machine_identifier: str
    product: str
    platform: str
    platform_version: str
    device: str
    model: str
    vendor: Optional[str] = None
    version: str
    address: str
    port: Optional[int] = None
    protocol: Optional[str] = None
    protocol_version: Optional[str] = None
    protocol_capabilities: Optional[str] = None
    title: str
    device_class: Optional[str] = None
    profile: Optional[str] = None
    remote_public_address: Optional[str] = None
    local: Optional[bool] = None
    relay: Optional[bool] = None
    secure: Optional[bool] = None
    user_id: Optional[int] = None


class PlexSessionLocation(BaseModel):
    """Session location information"""

    lan: Optional[bool] = None
    wan: Optional[bool] = None


class PlexSessionBandwidth(BaseModel):
    """Session bandwidth information"""

    account_id: Optional[int] = None
    location: Optional[str] = None
    bytes: Optional[int] = None


class PlexSessionInfo(BaseModel):
    """Plex session information model"""

    id: str
    bandwidth: Optional[int] = None
    location: Optional[str] = None
    state: str
    view_offset: int = 0
    progress_percent: Optional[float] = None
    started_at: Optional[datetime] = None
    last_viewed_at: Optional[datetime] = None
    transcoding: Optional[bool] = None
    container: Optional[str] = None
    video_decision: Optional[str] = None
    audio_decision: Optional[str] = None
    subtitle_decision: Optional[str] = None
    throttled: Optional[bool] = None
    synced_version: Optional[int] = None
    synced_version_profile: Optional[str] = None
    max_allowed_resolution: Optional[str] = None
    audio_codec: Optional[str] = None
    video_codec: Optional[str] = None
    protocol: Optional[str] = None
    mde: Optional[int] = None


class OriginalFileInfo(BaseModel):
    """Original file information"""

    file_path: Optional[str] = None
    file_name: Optional[str] = None
    size: Optional[int] = None
    container: Optional[str] = None
    duration: Optional[int] = None
    key: Optional[str] = None
    accessible: Optional[bool] = None
    exists: Optional[bool] = None
    has_thumbnail: Optional[bool] = None
    optimized_for_streaming: Optional[bool] = None
    width: Optional[int] = None
    height: Optional[int] = None


class PlexStreamPart(BaseModel):
    """Plex stream part model"""

    id: str
    key: Optional[str] = None
    duration: Optional[int] = None
    file: Optional[str] = None


class PlexStreamMedia(BaseModel):
    """Plex stream media model"""

    id: str
    duration: Optional[int] = None
    bitrate: Optional[int] = None
    parts: List["PlexStreamPart"] = []


# Auth Models
class PlexPin(BaseModel):
    """Plex PIN model"""

    id: int
    code: str


class PinCheckResponse(BaseModel):
    """PIN check response"""

    authenticated: bool
    auth_token: Optional[str] = None


class UserResponse(BaseModel):
    """User response wrapper"""

    user: PlexUser


class SessionInfo(BaseModel):
    """Session information model"""

    session_key: str
    user_id: str
    username: str
    media: MediaInfo
    player: PlayerInfo
    session: PlexSessionInfo
    original_file_info: Optional[OriginalFileInfo] = None


class CurrentSessionResponse(BaseModel):
    """Response for current session endpoint"""

    has_session: bool
    session: Optional[SessionInfo] = None
    message: Optional[str] = None


class AllSessionsResponse(BaseModel):
    """Response for all user sessions endpoint"""

    has_sessions: bool
    sessions: List[SessionInfo] = []
    message: Optional[str] = None


# Clip and Media Schemas
class ClipRequest(BaseModel):
    """Clip creation request with validation"""

    start_time: str = Field(..., description="Start time in HH:MM:SS or MM:SS format")
    end_time: str = Field(..., description="End time in HH:MM:SS or MM:SS format")
    quality: str = Field(default="medium", description="Video quality setting")
    format: str = Field(default="mp4", description="Output format")
    title: Optional[str] = Field(None, max_length=200, description="Custom clip title")
    include_metadata: bool = Field(default=True, description="Include metadata in the clip")
    session_key: Optional[str] = Field(
        None, description="Specific session key to use for clip creation"
    )

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not SecurityUtils.validate_time_format(v):
            raise ValueError("Invalid time format. Use HH:MM:SS or MM:SS")
        return v

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, v: str) -> str:
        return InputValidator.validate_quality_setting(v)

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        return InputValidator.validate_format_setting(v)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if v is not None:
            v = SecurityUtils.sanitize_user_input(v, max_length=200)
            if not v.strip():
                raise ValueError("Title cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        start_time = self.start_time
        end_time = self.end_time

        if start_time and end_time:
            if not SecurityUtils.validate_clip_duration(start_time, end_time):
                raise ValueError("Invalid time range or duration exceeds maximum limit")

        return self


class SnapshotRequest(BaseModel):
    """Snapshot creation request"""

    timestamp: str = Field(..., description="Timestamp in HH:MM:SS or MM:SS format")
    quality: str = Field(default="medium", description="Image quality setting")
    format: str = Field(default="jpg", description="Image format")
    session_key: Optional[str] = Field(
        None, description="Specific session key to use for snapshot creation"
    )

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        if not SecurityUtils.validate_time_format(v):
            raise ValueError("Invalid timestamp format. Use HH:MM:SS or MM:SS")
        return v

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, v: str) -> str:
        allowed = ["low", "medium", "high"]
        if v not in allowed:
            raise ValueError(f'Quality must be one of: {", ".join(allowed)}')
        return v

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        allowed = ["jpg", "jpeg", "png"]
        if v not in allowed:
            raise ValueError(f'Format must be one of: {", ".join(allowed)}')
        return v


class MultiFrameRequest(BaseModel):
    """Multi-frame snapshot request"""

    center_timestamp: str = Field(..., description="Center timestamp for frames")
    frame_count_before: int = Field(
        default=12, ge=0, le=20, description="Number of frames before center"
    )
    frame_count_after: int = Field(
        default=12, ge=0, le=20, description="Number of frames after center"
    )
    format: str = Field(default="jpg", description="Image format")
    quality: str = Field(default="medium", description="Image quality")
    frame_interval: float = Field(
        default=0.5, ge=0.1, le=10.0, description="Interval between frames in seconds"
    )
    session_key: Optional[str] = Field(
        None, description="Specific session key to use for multi-frame snapshot creation"
    )

    @field_validator("center_timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        if not SecurityUtils.validate_time_format(v):
            raise ValueError("Invalid timestamp format. Use HH:MM:SS or MM:SS")
        return v

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        allowed = ["jpg", "jpeg", "png"]
        if v not in allowed:
            raise ValueError(f'Format must be one of: {", ".join(allowed)}')
        return v

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, v: str) -> str:
        allowed = ["low", "medium", "high"]
        if v not in allowed:
            raise ValueError(f'Quality must be one of: {", ".join(allowed)}')
        return v


class EditRequest(BaseModel):
    """Video edit request"""

    source_clip_id: str = Field(..., min_length=1, max_length=100, description="Source clip ID")
    start_time: str = Field(..., description="Edit start time")
    end_time: str = Field(..., description="Edit end time")
    quality: str = Field(default="medium", description="Output quality")
    format: str = Field(default="mp4", description="Output format")
    include_metadata: bool = Field(default=True, description="Include metadata in the edit")

    @field_validator("source_clip_id")
    @classmethod
    def validate_clip_id(cls, v: str) -> str:
        # Sanitize clip ID - should be alphanumeric with hyphens/underscores
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid clip ID format")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not SecurityUtils.validate_time_format(v):
            raise ValueError("Invalid time format. Use HH:MM:SS or MM:SS")
        return v

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, v: str) -> str:
        return InputValidator.validate_quality_setting(v)

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        return InputValidator.validate_format_setting(v)

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        start_time = self.start_time
        end_time = self.end_time

        if start_time and end_time:
            if not SecurityUtils.validate_clip_duration(start_time, end_time):
                raise ValueError("Invalid time range or duration exceeds maximum limit")

        return self


class BulkDeleteRequest(BaseModel):
    """Bulk delete request"""

    clip_ids: List[str] = Field(..., description="Clip IDs to delete")

    @field_validator("clip_ids")
    @classmethod
    def validate_clip_ids(cls, v: list) -> list:
        if len(v) < 1:
            raise ValueError("At least one clip ID is required")
        if len(v) > 50:
            raise ValueError("Cannot delete more than 50 clips at once")
        validated_ids = []
        for clip_id in v:
            if not re.match(r"^[a-zA-Z0-9_-]+$", clip_id):
                raise ValueError(f"Invalid clip ID format: {clip_id}")
            validated_ids.append(clip_id)
        return validated_ids


class SnapshotCleanupRequest(BaseModel):
    """Snapshot cleanup request"""

    frame_ids: List[str] = Field(..., description="Frame IDs to cleanup")

    @field_validator("frame_ids")
    @classmethod
    def validate_frame_ids(cls, v: list) -> list:
        if len(v) < 1:
            raise ValueError("At least one frame ID is required")
        if len(v) > 100:
            raise ValueError("Cannot cleanup more than 100 frames at once")
        validated_ids = []
        for frame_id in v:
            if not re.match(r"^[a-zA-Z0-9_-]+$", frame_id):
                raise ValueError(f"Invalid frame ID format: {frame_id}")
            validated_ids.append(frame_id)
        return validated_ids


# Metadata Update Schemas
class ClipMetadataUpdate(BaseModel):
    """Clip metadata update request"""

    title: str = Field(..., min_length=1, max_length=200, description="Clip title")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = SecurityUtils.sanitize_user_input(v, max_length=200)
        if not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()


# Pagination Schema
class PaginationParams(BaseModel):
    """Pagination parameters"""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @model_validator(mode="after")
    def validate_pagination(self) -> Self:
        validated_page, validated_page_size = InputValidator.validate_pagination(
            self.page, self.page_size
        )

        self.page = validated_page
        self.page_size = validated_page_size

        return self


# Preview Frame Request
class PreviewFrameRequest(BaseModel):
    """Preview frame generation request"""

    start_time: Optional[str] = Field(None, description="Start time for preview")
    end_time: Optional[str] = Field(None, description="End time for preview")

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if v is not None and not SecurityUtils.validate_time_format(v):
            raise ValueError("Invalid time format. Use HH:MM:SS or MM:SS")
        return v

    @model_validator(mode="after")
    def validate_at_least_one_time(self) -> Self:
        if not self.start_time and not self.end_time:
            raise ValueError("At least one time (start_time or end_time) must be provided")

        return self


# File Access Schema
class SecureFileRequest(BaseModel):
    """Secure file access request"""

    file_id: str = Field(..., min_length=1, max_length=100, description="File identifier")
    signature: Optional[str] = Field(None, description="HMAC signature for verification")

    @field_validator("file_id")
    @classmethod
    def validate_file_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid file ID format")
        return v


# Data Models (referenced by response schemas)
class ClipMetadata(BaseModel):
    """Metadata embedded in the clip file"""

    title: str
    show_name: Optional[str] = None
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    original_timestamp: str
    username: str
    duration: float
    created_at: str


class FrameInfo(BaseModel):
    """Information about a single frame"""

    frame_id: str
    timestamp: str
    download_url: str
    file_path: str
    file_size: int


# Response Schemas (keeping existing from models.py but with validation)
class ClipResponse(BaseModel):
    """Clip creation/retrieval response"""

    clip_id: Optional[str] = None
    status: str
    file_path: Optional[str] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[float] = None
    metadata: Optional[ClipMetadata] = None
    error_message: Optional[str] = None
    progress: Optional[float] = None
    created_at: Optional[str] = None


class SnapshotResponse(BaseModel):
    """Snapshot creation/retrieval response"""

    snapshot_id: Optional[str] = None
    status: str
    file_path: Optional[str] = None
    download_url: Optional[str] = None
    file_size: Optional[int] = None
    timestamp: Optional[str] = None
    error_message: Optional[str] = None


class EditResponse(BaseModel):
    """Edit operation response"""

    edit_id: Optional[str] = None
    source_clip_id: Optional[str] = None
    status: str
    file_path: Optional[str] = None
    download_url: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[float] = None
    metadata: Optional[ClipMetadata] = None
    error_message: Optional[str] = None
    progress: Optional[float] = None
    created_at: Optional[str] = None


class MultiFrameResponse(BaseModel):
    """Multi-frame response"""

    status: str
    frames: Optional[List[Dict[str, str]]] = None
    message: Optional[str] = None
    error_message: Optional[str] = None


class ClipListResponse(BaseModel):
    """Clip list response with pagination"""

    clips: List[ClipResponse]
    total_count: int
    page: int = 1
    page_size: int = 20
    total_pages: Optional[int] = None

    @model_validator(mode="after")
    def calculate_total_pages(self) -> Self:
        if self.page_size > 0:
            self.total_pages = (self.total_count + self.page_size - 1) // self.page_size
        else:
            self.total_pages = 0

        return self
