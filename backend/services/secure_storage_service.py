"""
Secure storage service for ClipForge
Handles secure file access with proper validation and user authorization
"""

import hashlib
import hmac
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Union

from core.config import settings
from core.security import SecurityUtils
from fastapi import HTTPException
from fastapi.responses import FileResponse
from infrastructure.database import Clip, Edit, Snapshot, get_db_session
from infrastructure.repositories import StorageStatsRepository
from sqlalchemy import func

logger = logging.getLogger(__name__)


class SecureStorageService:
    """Secure file storage and access service"""

    def __init__(
        self,
        base_storage_path: Optional[str] = None,
        retention_days: Optional[int] = None,
    ):
        """
        Initialize secure storage service

        Args:
            base_storage_path: Base path for file storage (defaults to config)
            retention_days: Number of days to retain files (defaults to config)
        """
        self.base_path = Path(base_storage_path or settings.absolute_clips_path).resolve()
        self.secret_key = settings.jwt_secret
        self.retention_days = retention_days or settings.clip_retention_days

        # Ensure base path exists and is secure
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"SecureStorageService initialized with base path: {self.base_path}")

    def generate_access_signature(
        self, file_id: str, user_id: str, expires_at: Optional[int] = None
    ) -> str:
        """
        Generate secure access signature for file

        Args:
            file_id: Unique file identifier
            user_id: User requesting access
            expires_at: Optional expiration timestamp

        Returns:
            HMAC signature for file access
        """
        message_parts = [file_id, user_id]
        if expires_at:
            message_parts.append(str(expires_at))

        message = ":".join(message_parts).encode("utf-8")
        return hmac.new(self.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def verify_access_signature(
        self,
        file_id: str,
        user_id: str,
        signature: str,
        expires_at: Optional[int] = None,
    ) -> bool:
        """
        Verify file access signature

        Args:
            file_id: File identifier
            user_id: User requesting access
            signature: Provided signature
            expires_at: Optional expiration timestamp

        Returns:
            True if signature is valid and not expired
        """
        if expires_at and expires_at < int(time.time()):
            logger.warning(f"Access signature expired for file {file_id}, user {user_id}")
            return False

        expected_signature = self.generate_access_signature(file_id, user_id, expires_at)
        is_valid = hmac.compare_digest(signature, expected_signature)

        if not is_valid:
            logger.warning(f"Invalid access signature for file {file_id}, user {user_id}")

        return is_valid

    def get_secure_file_path(self, relative_path: str) -> Path:
        """
        Get secure file path with validation

        Args:
            relative_path: Relative path from base storage

        Returns:
            Validated absolute path

        Raises:
            HTTPException: If path is invalid or unsafe
        """
        try:
            # Validate and resolve path
            secure_path = SecurityUtils.validate_file_path(
                self.base_path / relative_path, self.base_path
            )

            if not secure_path.exists():
                raise HTTPException(status_code=404, detail="File not found")

            return secure_path

        except ValueError as e:
            logger.warning(f"Path validation failed: {e}")
            raise HTTPException(status_code=403, detail="Access denied - invalid file path")
        except Exception as e:
            logger.error(f"Unexpected error in file path validation: {e}")
            raise HTTPException(status_code=500, detail="File access error")

    def create_secure_file_response(
        self,
        file_path: Union[str, Path],
        filename: Optional[str] = None,
        media_type: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> FileResponse:
        """
        Create secure file response with proper headers

        Args:
            file_path: Path to file
            filename: Custom filename for download
            media_type: MIME type
            headers: Additional headers

        Returns:
            FileResponse with security headers
        """
        file_path = Path(file_path)

        # Auto-detect media type if not provided
        if not media_type:
            ext = file_path.suffix.lower()
            media_type_map = {
                ".mp4": "video/mp4",
                ".webm": "video/webm",
                ".mov": "video/quicktime",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
            }
            media_type = media_type_map.get(ext, "application/octet-stream")

        # Set secure filename if not provided
        if not filename:
            filename = SecurityUtils.sanitize_filename(file_path.name)

        # Security headers
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Cache-Control": "private, max-age=3600",
        }

        if headers:
            security_headers.update(headers)

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type=media_type,
            headers=security_headers,
        )

    def stream_video_file(
        self, clip_id: str, user_id: str, file_path: str, force_download: bool = False
    ) -> FileResponse:
        """
        Stream video file with security validation

        Args:
            clip_id: Clip identifier
            user_id: User requesting access
            file_path: Path to video file

        Returns:
            Secure FileResponse for video streaming
        """
        try:
            # Validate file path security
            secure_path = self.get_secure_file_path(file_path)

            # Log access attempt
            logger.info(
                f"Video stream request - Clip: {clip_id}, User: {user_id}, Path: {secure_path}"
            )

            # Set Content-Disposition based on force_download parameter
            disposition = "attachment" if force_download else "inline"

            return self.create_secure_file_response(
                file_path=secure_path,
                filename=f"{clip_id}.mp4",
                media_type="video/mp4",
                headers={
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": f'{disposition}; filename="{clip_id}.mp4"',
                },
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to stream video {clip_id} for user {user_id}: {e}")
            raise HTTPException(status_code=500, detail="Video streaming failed")

    def stream_image_file(self, image_id: str, user_id: str, file_path: str) -> FileResponse:
        """
        Stream image file with security validation

        Args:
            image_id: Image identifier
            user_id: User requesting access
            file_path: Path to image file

        Returns:
            Secure FileResponse for image streaming
        """
        try:
            # Validate file path security
            secure_path = self.get_secure_file_path(file_path)

            # Log access attempt
            logger.info(
                f"Image stream request - Image: {image_id}, User: {user_id}, Path: {secure_path}"
            )

            # Determine image type
            ext = secure_path.suffix.lower()
            media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"

            return self.create_secure_file_response(
                file_path=secure_path,
                filename=f"{image_id}{ext}",
                media_type=media_type,
                headers={"Content-Disposition": f'inline; filename="{image_id}{ext}"'},
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to stream image {image_id} for user {user_id}: {e}")
            raise HTTPException(status_code=500, detail="Image streaming failed")

    def stream_temporary_file(self, temp_file_id: str, user_id: str) -> FileResponse:
        """
        Stream temporary file (like preview frames) with security validation

        Args:
            temp_file_id: Temporary file identifier
            user_id: User requesting access

        Returns:
            Secure FileResponse for temporary file
        """
        try:
            # Look for temporary files in snapshots directory
            snapshots_dir = self.base_path / "snapshots"

            logger.debug(f"Looking for temporary file {temp_file_id} in {snapshots_dir}")

            # Common patterns for temporary files
            temp_patterns = [
                f"preview_start_{temp_file_id}.jpg",
                f"preview_end_{temp_file_id}.jpg",
                f"frame_{temp_file_id}.jpg",
                f"multiframe_{temp_file_id}.jpg",
            ]

            temp_file_path = None
            for pattern in temp_patterns:
                potential_path = snapshots_dir / pattern
                logger.debug(f"Checking pattern: {potential_path}")
                if potential_path.exists():
                    temp_file_path = potential_path
                    logger.debug(f"Found matching file: {temp_file_path}")
                    break

            if not temp_file_path:
                logger.warning(
                    f"Temporary file not found for ID {temp_file_id}. "
                    f"Checked patterns: {temp_patterns} in {snapshots_dir}"
                )
                raise HTTPException(status_code=404, detail="Temporary file not found")

            # Validate path security
            secure_path = SecurityUtils.validate_file_path(temp_file_path, self.base_path)

            # Log access attempt
            logger.info(
                f"Temporary file stream - File: {temp_file_id}, User: {user_id}, Path: {secure_path}"
            )

            return self.create_secure_file_response(
                file_path=secure_path,
                filename=f"{temp_file_id}.jpg",
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "private, max-age=300",
                    "Content-Disposition": f'inline; filename="{temp_file_id}.jpg"',
                },
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to stream temporary file {temp_file_id} for user {user_id}: {e}",
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail="Temporary file streaming failed")

    def cleanup_temporary_files(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """
        Clean up old temporary files

        Args:
            max_age_hours: Maximum age for temporary files in hours

        Returns:
            Cleanup statistics
        """
        import time

        cleanup_stats: Dict[str, Any] = {
            "files_checked": 0,
            "files_deleted": 0,
            "bytes_freed": 0,
            "errors": [],
        }

        try:
            cutoff_time = time.time() - (max_age_hours * 3600)
            snapshots_dir = self.base_path / "snapshots"

            if not snapshots_dir.exists():
                return cleanup_stats

            # Look for temporary files (preview_, frame_, multiframe_ patterns)
            temp_patterns = ["preview_*.jpg", "frame_*.jpg", "multiframe_*.jpg"]

            for pattern in temp_patterns:
                for temp_file in snapshots_dir.glob(pattern):
                    cleanup_stats["files_checked"] = cleanup_stats["files_checked"] + 1

                    try:
                        if temp_file.stat().st_mtime < cutoff_time:
                            file_size = temp_file.stat().st_size
                            temp_file.unlink()
                            cleanup_stats["files_deleted"] = cleanup_stats["files_deleted"] + 1
                            cleanup_stats["bytes_freed"] = cleanup_stats["bytes_freed"] + file_size
                            logger.debug(f"Deleted temporary file: {temp_file}")
                    except Exception as e:
                        error_msg = f"Failed to delete {temp_file}: {e}"
                        cleanup_stats["errors"].append(error_msg)
                        logger.warning(error_msg)

            logger.info(f"Temporary file cleanup completed: {cleanup_stats}")
            return cleanup_stats

        except Exception as e:
            error_msg = f"Temporary file cleanup failed: {e}"
            cleanup_stats["errors"].append(error_msg)
            logger.error(error_msg)
            return cleanup_stats

    def get_storage_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get storage statistics, optionally filtered by user.

        Args:
            user_id: Optional user ID to filter stats

        Returns:
            Dictionary containing storage statistics
        """
        with get_db_session() as session:
            stats_repo = StorageStatsRepository(session)

            if user_id:
                # Get user-specific stats from repository
                user_stats = stats_repo.get_user_storage_stats(user_id)

                # Format response for consistency
                total_size = user_stats.get("total_size", 0)

                stats = {
                    "clips_count": user_stats.get("clips", {}).get("count", 0),
                    "snapshots_count": user_stats.get("snapshots", {}).get("count", 0),
                    "edits_count": user_stats.get("edits", {}).get("count", 0),
                    "total_size_bytes": total_size,
                    "total_size_mb": (round(total_size / (1024 * 1024), 2) if total_size else 0),
                    "retention_days": self.retention_days,
                }
            else:
                # Get global stats - aggregate all users
                clips_count = session.query(Clip).count()
                edits_count = session.query(Edit).count()
                snapshots_count = session.query(Snapshot).count()

                # Get sizes
                clips_size = (
                    session.query(func.sum(Clip.file_size))
                    .filter(Clip.file_size.isnot(None))
                    .scalar()
                    or 0
                )

                edits_size = (
                    session.query(func.sum(Edit.file_size))
                    .filter(Edit.file_size.isnot(None))
                    .scalar()
                    or 0
                )

                snapshots_size = (
                    session.query(func.sum(Snapshot.file_size))
                    .filter(Snapshot.file_size.isnot(None))
                    .scalar()
                    or 0
                )

                total_size = clips_size + edits_size + snapshots_size

                stats = {
                    "clips_count": clips_count,
                    "snapshots_count": snapshots_count,
                    "edits_count": edits_count,
                    "total_size_bytes": total_size,
                    "total_size_mb": (round(total_size / (1024 * 1024), 2) if total_size else 0),
                    "retention_days": self.retention_days,
                }

            # Add disk usage information
            try:
                disk_usage = shutil.disk_usage(str(self.base_path))
                stats["free_space_bytes"] = disk_usage.free
                stats["total_space_bytes"] = disk_usage.total
            except Exception as e:
                logger.warning(f"Could not get disk usage: {e}")
                stats["free_space_bytes"] = None
                stats["total_space_bytes"] = None

            return stats

    async def cleanup_old_files(self, user_id: Optional[str] = None) -> Dict[str, int]:
        """
        Clean up files older than retention period.

        Args:
            user_id: Optional user ID to limit cleanup to specific user

        Returns:
            Dictionary with counts of deleted files by type
        """
        if self.retention_days <= 0:
            return {"clips_deleted": 0, "snapshots_deleted": 0, "edits_deleted": 0}

        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)

        clips_deleted = 0
        snapshots_deleted = 0
        edits_deleted = 0

        try:
            with get_db_session() as session:
                # Build base queries
                clips_query = session.query(Clip).filter(Clip.created_at < cutoff_date)
                snapshots_query = session.query(Snapshot).filter(Snapshot.created_at < cutoff_date)
                edits_query = session.query(Edit).filter(Edit.created_at < cutoff_date)

                # Filter by user if specified
                if user_id:
                    clips_query = clips_query.filter(Clip.user_id == user_id)
                    snapshots_query = snapshots_query.filter(Snapshot.user_id == user_id)
                    edits_query = edits_query.filter(Edit.user_id == user_id)

                # Delete old clips
                old_clips = clips_query.all()
                for clip in old_clips:
                    try:
                        if clip.file_path and os.path.exists(clip.file_path):
                            os.remove(clip.file_path)
                            logger.info(f"Deleted clip file: {clip.file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting clip file {clip.file_path}: {e}")

                    session.delete(clip)
                    clips_deleted += 1

                # Delete old snapshots
                old_snapshots = snapshots_query.all()
                for snapshot in old_snapshots:
                    try:
                        if snapshot.file_path and os.path.exists(snapshot.file_path):
                            os.remove(snapshot.file_path)
                            logger.info(f"Deleted snapshot file: {snapshot.file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting snapshot file {snapshot.file_path}: {e}")

                    session.delete(snapshot)
                    snapshots_deleted += 1

                # Delete old edits
                old_edits = edits_query.all()
                for edit in old_edits:
                    try:
                        if edit.file_path and os.path.exists(edit.file_path):
                            os.remove(edit.file_path)
                            logger.info(f"Deleted edit file: {edit.file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting edit file {edit.file_path}: {e}")

                    session.delete(edit)
                    edits_deleted += 1

                # Commit all deletions
                session.commit()

                logger.info(
                    f"Cleanup completed: deleted {clips_deleted} clips, "
                    f"{snapshots_deleted} snapshots, {edits_deleted} edits"
                )

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

        return {
            "clips_deleted": clips_deleted,
            "snapshots_deleted": snapshots_deleted,
            "edits_deleted": edits_deleted,
        }
