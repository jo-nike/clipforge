"""
Domain Interfaces - Abstract base classes and protocols for service layer
Defines contracts for business logic services and external integrations
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from domain.schemas import (
    ClipRequest,
    ClipResponse,
    EditRequest,
    EditResponse,
    MultiFrameRequest,
    MultiFrameResponse,
    PlexUser,
    SessionInfo,
    SnapshotRequest,
    SnapshotResponse,
)


class IPlexService(ABC):
    """Abstract interface for Plex integration service"""

    @abstractmethod
    async def create_pin(self) -> Optional[Dict[str, Any]]:
        """Create a new PIN for Plex OAuth authentication"""
        pass

    @abstractmethod
    async def check_pin(self, pin_id: int) -> Optional[str]:
        """Check if a PIN has been authenticated and return auth token"""
        pass

    @abstractmethod
    async def authenticate_user(self, auth_token: str) -> Optional[PlexUser]:
        """Authenticate user with Plex token and return user info"""
        pass

    @abstractmethod
    async def get_current_session(self, plex_token: str, username: str) -> Optional[SessionInfo]:
        """Get user's current playback session"""
        pass

    @abstractmethod
    async def get_all_user_sessions(self, plex_token: str, username: str) -> List[SessionInfo]:
        """Get all user's playback sessions"""
        pass


class IClipProcessingService(ABC):
    """Abstract interface for clip processing service"""

    @abstractmethod
    async def create_clip(
        self,
        session: SessionInfo,
        request: ClipRequest,
        plex_token: str,
        user_id: str,
    ) -> ClipResponse:
        """Create a video clip from current session"""
        pass

    @abstractmethod
    async def create_snapshot(
        self,
        session: SessionInfo,
        request: SnapshotRequest,
        plex_token: str,
        user_id: str,
    ) -> SnapshotResponse:
        """Create a snapshot from current session"""
        pass

    @abstractmethod
    async def create_multi_frame_snapshots(
        self,
        session: SessionInfo,
        request: MultiFrameRequest,
        plex_token: str,
        user_id: str,
    ) -> MultiFrameResponse:
        """Create multiple frames around a center timestamp"""
        pass

    @abstractmethod
    async def edit_clip(
        self, source_clip_id: str, request: EditRequest, user_id: str
    ) -> EditResponse:
        """Edit an existing clip by trimming it"""
        pass

    @abstractmethod
    async def generate_preview_frames(
        self,
        session: SessionInfo,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        plex_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate preview frames at start and end times"""
        pass


class IStorageService(ABC):
    """Abstract interface for storage management service"""

    @abstractmethod
    async def get_storage_stats(self, user_id: str) -> Dict[str, Any]:
        """Get storage statistics for a user"""
        pass

    @abstractmethod
    async def cleanup_old_files(self, user_id: str) -> Dict[str, Any]:
        """Clean up old files for a user"""
        pass

    @abstractmethod
    def stream_video_file(self, clip_id: str, user_id: str, file_path: str) -> Any:
        """Stream a video file with proper security checks"""
        pass

    @abstractmethod
    def stream_snapshot_file(self, snapshot_id: str, user_id: str) -> Any:
        """Stream a snapshot file with proper security checks"""
        pass


class IClipManagementService(ABC):
    """Abstract interface for clip management operations"""

    @abstractmethod
    async def list_user_clips(
        self, user_id: str, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List user's clips with pagination"""
        pass

    @abstractmethod
    async def get_clip(self, clip_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get clip information by ID"""
        pass

    @abstractmethod
    async def update_clip_metadata(
        self, clip_id: str, user_id: str, metadata: Dict[str, Any]
    ) -> bool:
        """Update clip metadata"""
        pass

    @abstractmethod
    async def delete_clip(self, clip_id: str, user_id: str) -> bool:
        """Delete a clip"""
        pass

    @abstractmethod
    async def bulk_delete_clips(self, clip_ids: List[str], user_id: str) -> Tuple[int, List[str]]:
        """Delete multiple clips, return (deleted_count, failed_clip_ids)"""
        pass

    @abstractmethod
    async def get_edited_videos(self, source_clip_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get all edited videos from a source clip"""
        pass

    @abstractmethod
    async def delete_edited_video(self, edit_id: str, user_id: str) -> bool:
        """Delete an individual edited video"""
        pass


class INotificationService(ABC):
    """Abstract interface for event notifications"""

    @abstractmethod
    async def notify_clip_created(self, user_id: str, clip_id: str) -> None:
        """Notify about clip creation"""
        pass

    @abstractmethod
    async def notify_clip_processed(self, user_id: str, clip_id: str, status: str) -> None:
        """Notify about clip processing completion"""
        pass

    @abstractmethod
    async def notify_storage_limit_reached(self, user_id: str, usage: Dict[str, Any]) -> None:
        """Notify about storage limit being reached"""
        pass


class IHealthCheckService(ABC):
    """Abstract interface for health check operations"""

    @abstractmethod
    async def check_database_health(self) -> Dict[str, Any]:
        """Check database connectivity and health"""
        pass

    @abstractmethod
    async def check_storage_health(self) -> Dict[str, Any]:
        """Check storage system health"""
        pass

    @abstractmethod
    async def check_external_services_health(self) -> Dict[str, Any]:
        """Check external service connectivity"""
        pass

    @abstractmethod
    async def get_comprehensive_health_status(self) -> Dict[str, Any]:
        """Get overall system health status"""
        pass
