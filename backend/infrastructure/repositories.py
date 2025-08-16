"""
Secure repository pattern implementation for ClipForge
Provides data access layer with SQL injection protection
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.security import SecurityUtils
from infrastructure.database import Clip, Edit, SecureQueryBuilder, Snapshot, User
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with common secure operations"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.query_builder = SecureQueryBuilder()

    def _validate_user_access(self, user_id: str, resource_user_id: str) -> bool:
        """Validate user has access to resource"""
        if not user_id or not resource_user_id:
            return False
        return user_id == resource_user_id

    def _sanitize_string_input(self, input_str: str, max_length: int = 200) -> str:
        """Sanitize string input for database storage"""
        if not input_str:
            return ""
        return SecurityUtils.sanitize_user_input(input_str, max_length)


class UserRepository(BaseRepository):
    """Repository for user operations"""

    def get_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID with validation"""
        try:
            if not user_id or len(user_id) > 100:
                return None

            user = self.session.query(User).filter(User.user_id == user_id).first()

            return user

        except Exception as e:
            logger.error(f"Error getting user by ID {user_id}: {e}")
            return None

    def create_or_update(self, user_id: str, username: str, email: str) -> User:
        """Create new user or update existing user's last login"""
        try:
            # Sanitize inputs
            user_id = self._sanitize_string_input(user_id, 100)
            username = self._sanitize_string_input(username, 100)
            email = self._sanitize_string_input(email, 255)

            if not all([user_id, username, email]):
                raise ValueError("User ID, username, and email are required")

            # Check if user exists
            user = self.get_by_id(user_id)

            if user:
                # Update last login
                user.last_login = datetime.utcnow()  # type: ignore[assignment]
                logger.debug(f"Updated last login for user {username}")
            else:
                # Create new user
                user = User(
                    user_id=user_id,
                    username=username,
                    email=email,
                    created_at=datetime.utcnow(),
                    last_login=datetime.utcnow(),
                    is_active=True,
                )
                self.session.add(user)
                logger.info(f"Created new user: {username}")

            self.session.flush()
            return user

        except Exception as e:
            logger.error(f"Error creating/updating user {username}: {e}")
            raise

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate user account"""
        try:
            user = self.get_by_id(user_id)
            if user:
                user.is_active = False  # type: ignore[assignment]
                self.session.flush()
                logger.info(f"Deactivated user {user.username}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error deactivating user {user_id}: {e}")
            return False


class ClipRepository(BaseRepository):
    """Repository for clip operations with security validation"""

    def create(self, clip_data: Dict[str, Any]) -> Clip:
        """Create new clip with validation"""
        try:
            # Validate required fields
            required_fields = ["id", "user_id", "title", "file_path"]
            for field in required_fields:
                if field not in clip_data or not clip_data[field]:
                    raise ValueError(f"Required field missing: {field}")

            # Sanitize inputs
            clip = Clip(
                id=self._sanitize_string_input(clip_data["id"], 100),
                user_id=self._sanitize_string_input(clip_data["user_id"], 100),
                title=self._sanitize_string_input(clip_data["title"], 200),
                file_path=self._sanitize_string_input(clip_data["file_path"], 500),
                file_size=clip_data.get("file_size"),
                duration=clip_data.get("duration"),
                show_name=self._sanitize_string_input(clip_data.get("show_name", ""), 200),
                season_number=clip_data.get("season_number"),
                episode_number=clip_data.get("episode_number"),
                original_timestamp=self._sanitize_string_input(
                    clip_data.get("original_timestamp", ""), 50
                ),
                status=clip_data.get("status", "completed"),
                created_at=datetime.utcnow(),
            )

            self.session.add(clip)
            self.session.flush()

            logger.info(f"Created clip {clip.id} for user {clip.user_id}")
            return clip

        except Exception as e:
            logger.error(f"Error creating clip: {e}")
            raise

    def get_by_id(self, clip_id: str, user_id: str) -> Optional[Clip]:
        """Get clip by ID with user ownership validation"""
        try:
            if not clip_id or not user_id:
                return None

            clip = (
                self.session.query(Clip)
                .filter(
                    and_(
                        Clip.id == clip_id,
                        self.query_builder.build_user_filter(self.session, user_id, Clip),
                    )
                )
                .first()
            )

            return clip

        except Exception as e:
            logger.error(f"Error getting clip {clip_id} for user {user_id}: {e}")
            return None

    def list_user_clips(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 20,
        search_term: Optional[str] = None,
    ) -> Tuple[List[Clip], int]:
        """List clips for user with pagination and search"""
        try:
            # Build base query
            query = self.session.query(Clip).filter(
                self.query_builder.build_user_filter(self.session, user_id, Clip)
            )

            # Add search filter if provided
            if search_term:
                search_filter = self.query_builder.build_search_filter(Clip.title, search_term)
                if search_filter is not None:
                    query = query.filter(search_filter)

            # Get total count
            total_count = query.count()

            # Apply pagination and ordering
            clips = self.query_builder.build_pagination_query(
                query.order_by(desc(Clip.created_at)), offset, limit
            ).all()

            logger.debug(f"Listed {len(clips)} clips for user {user_id} (total: {total_count})")
            return clips, total_count

        except Exception as e:
            logger.error(f"Error listing clips for user {user_id}: {e}")
            return [], 0

    def update_metadata(self, clip_id: str, user_id: str, update_data: Dict[str, Any]) -> bool:
        """Update clip metadata with validation"""
        try:
            clip = self.get_by_id(clip_id, user_id)
            if not clip:
                return False

            # Update allowed fields only
            allowed_fields = ["title"]
            for field, value in update_data.items():
                if field in allowed_fields and value is not None:
                    if field == "title":
                        clip.title = self._sanitize_string_input(value, 200)

            self.session.flush()
            logger.info(f"Updated clip {clip_id} metadata for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating clip {clip_id} for user {user_id}: {e}")
            return False

    def delete_clip(self, clip_id: str, user_id: str) -> bool:
        """Delete clip with user validation and cleanup of all associated files"""
        try:
            clip = self.get_by_id(clip_id, user_id)
            if not clip:
                return False

            # Delete the main clip file if it exists
            if clip.file_path and os.path.exists(clip.file_path):
                try:
                    os.remove(clip.file_path)
                    logger.info(f"Deleted clip file: {clip.file_path}")
                except Exception as file_error:
                    logger.error(f"Error deleting clip file {clip.file_path}: {file_error}")

            # Delete all associated edit files (cascading deletes handle DB records)
            try:
                edits = (
                    self.session.query(Edit)
                    .filter(
                        and_(
                            Edit.source_clip_id == clip_id,
                            self.query_builder.build_user_filter(self.session, user_id, Edit),
                        )
                    )
                    .all()
                )

                for edit in edits:
                    if edit.file_path and os.path.exists(edit.file_path):
                        try:
                            os.remove(edit.file_path)
                            logger.info(f"Deleted associated edit file: {edit.file_path}")
                        except Exception as file_error:
                            logger.error(f"Error deleting edit file {edit.file_path}: {file_error}")
            except Exception as e:
                logger.error(f"Error cleaning up edit files for clip {clip_id}: {e}")

            # NOTE: Snapshots are not directly related to clips in the current schema
            # They are user-scoped entities and are not deleted when clips are deleted

            # Delete the database record (cascading deletes will handle edits and snapshots)
            self.session.delete(clip)
            self.session.flush()

            logger.info(f"Deleted clip {clip_id} and all associated files for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting clip {clip_id} for user {user_id}: {e}")
            return False

    def bulk_delete_clips(self, clip_ids: List[str], user_id: str) -> Tuple[int, List[str]]:
        """Bulk delete clips with validation"""
        deleted_count = 0
        failed_clips = []

        for clip_id in clip_ids:
            try:
                if self.delete_clip(clip_id, user_id):
                    deleted_count += 1
                else:
                    failed_clips.append(clip_id)
            except Exception as e:
                logger.error(f"Failed to delete clip {clip_id}: {e}")
                failed_clips.append(clip_id)

        logger.info(f"Bulk deleted {deleted_count}/{len(clip_ids)} clips for user {user_id}")
        return deleted_count, failed_clips


class EditRepository(BaseRepository):
    """Repository for edit operations"""

    def create(self, edit_data: Dict[str, Any]) -> Edit:
        """Create new edit with validation"""
        try:
            # Validate required fields
            required_fields = ["id", "user_id", "source_clip_id", "file_path"]
            for field in required_fields:
                if field not in edit_data or not edit_data[field]:
                    raise ValueError(f"Required field missing: {field}")

            edit = Edit(
                id=self._sanitize_string_input(edit_data["id"], 100),
                user_id=self._sanitize_string_input(edit_data["user_id"], 100),
                source_clip_id=self._sanitize_string_input(edit_data["source_clip_id"], 100),
                file_path=self._sanitize_string_input(edit_data["file_path"], 500),
                file_size=edit_data.get("file_size"),
                duration=edit_data.get("duration"),
                start_time=self._sanitize_string_input(edit_data.get("start_time", ""), 20),
                end_time=self._sanitize_string_input(edit_data.get("end_time", ""), 20),
                quality=edit_data.get("quality", "medium"),
                format=edit_data.get("format", "mp4"),
                status=edit_data.get("status", "completed"),
                created_at=datetime.utcnow(),
            )

            self.session.add(edit)
            self.session.flush()

            logger.info(f"Created edit {edit.id} for user {edit.user_id}")
            return edit

        except Exception as e:
            logger.error(f"Error creating edit: {e}")
            raise

    def get_by_id(self, edit_id: str, user_id: str) -> Optional[Edit]:
        """Get edit by ID with user validation"""
        try:
            edit = (
                self.session.query(Edit)
                .filter(
                    and_(
                        Edit.id == edit_id,
                        self.query_builder.build_user_filter(self.session, user_id, Edit),
                    )
                )
                .first()
            )

            return edit

        except Exception as e:
            logger.error(f"Error getting edit {edit_id} for user {user_id}: {e}")
            return None

    def get_edits_by_source_clip(self, source_clip_id: str, user_id: str) -> List[Edit]:
        """Get all edits for a source clip"""
        try:
            edits = (
                self.session.query(Edit)
                .filter(
                    and_(
                        Edit.source_clip_id == source_clip_id,
                        self.query_builder.build_user_filter(self.session, user_id, Edit),
                    )
                )
                .order_by(desc(Edit.created_at))
                .all()
            )

            return edits

        except Exception as e:
            logger.error(f"Error getting edits for clip {source_clip_id}: {e}")
            return []

    def delete_edit(self, edit_id: str, user_id: str) -> bool:
        """Delete edit with user validation and file cleanup"""
        try:
            edit = self.get_by_id(edit_id, user_id)
            if not edit:
                return False

            # Delete the physical file if it exists
            if edit.file_path and os.path.exists(edit.file_path):
                try:
                    os.remove(edit.file_path)
                    logger.info(f"Deleted edit file: {edit.file_path}")
                except Exception as file_error:
                    logger.error(f"Error deleting edit file {edit.file_path}: {file_error}")
                    # Continue with database deletion even if file deletion fails

            # Delete the database record
            self.session.delete(edit)
            self.session.flush()

            logger.info(f"Deleted edit {edit_id} for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting edit {edit_id} for user {user_id}: {e}")
            return False


class SnapshotRepository(BaseRepository):
    """Repository for snapshot operations"""

    def create(self, snapshot_data: Dict[str, Any]) -> Snapshot:
        """Create new snapshot with validation"""
        try:
            # Validate required fields
            required_fields = ["id", "user_id", "file_path"]
            for field in required_fields:
                if field not in snapshot_data or not snapshot_data[field]:
                    raise ValueError(f"Required field missing: {field}")

            snapshot = Snapshot(
                id=self._sanitize_string_input(snapshot_data["id"], 100),
                user_id=self._sanitize_string_input(snapshot_data["user_id"], 100),
                file_path=self._sanitize_string_input(snapshot_data["file_path"], 500),
                file_size=snapshot_data.get("file_size"),
                timestamp=self._sanitize_string_input(snapshot_data.get("timestamp", ""), 20),
                format=snapshot_data.get("format", "jpg"),
                quality=snapshot_data.get("quality", "high"),
                media_title=self._sanitize_string_input(snapshot_data.get("media_title", ""), 200),
                show_name=self._sanitize_string_input(snapshot_data.get("show_name", ""), 200),
                season_number=snapshot_data.get("season_number"),
                episode_number=snapshot_data.get("episode_number"),
                status=snapshot_data.get("status", "completed"),
                created_at=datetime.utcnow(),
            )

            self.session.add(snapshot)
            self.session.flush()

            logger.info(f"Created snapshot {snapshot.id} for user {snapshot.user_id}")
            return snapshot

        except Exception as e:
            logger.error(f"Error creating snapshot: {e}")
            raise

    def get_by_id(self, snapshot_id: str, user_id: str) -> Optional[Snapshot]:
        """Get snapshot by ID with user validation"""
        try:
            snapshot = (
                self.session.query(Snapshot)
                .filter(
                    and_(
                        Snapshot.id == snapshot_id,
                        self.query_builder.build_user_filter(self.session, user_id, Snapshot),
                    )
                )
                .first()
            )

            return snapshot

        except Exception as e:
            logger.error(f"Error getting snapshot {snapshot_id} for user {user_id}: {e}")
            return None

    def delete(self, snapshot_id: str, user_id: str) -> bool:
        """Delete snapshot with user validation"""
        try:
            snapshot = self.get_by_id(snapshot_id, user_id)
            if not snapshot:
                return False

            self.session.delete(snapshot)
            self.session.flush()

            logger.info(f"Deleted snapshot {snapshot_id} for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting snapshot {snapshot_id} for user {user_id}: {e}")
            return False


class StorageStatsRepository(BaseRepository):
    """Repository for storage statistics"""

    def get_user_video_count(self, user_id: str) -> int:
        """Get total number of videos (clips + edits) for user"""
        try:
            if not user_id:
                return 0

            # Count clips
            clip_count = (
                self.session.query(func.count(Clip.id)).filter(Clip.user_id == user_id).scalar()
                or 0
            )

            # Count edits
            edit_count = (
                self.session.query(func.count(Edit.id)).filter(Edit.user_id == user_id).scalar()
                or 0
            )

            return clip_count + edit_count

        except Exception as e:
            logger.error(f"Error getting user video count for {user_id}: {e}")
            return 0

    def get_user_storage_stats(self, user_id: str) -> Dict[str, Any]:
        """Get storage statistics for user"""
        try:
            stats: Dict[str, Any] = {
                "clips": {"count": 0, "total_size": 0},
                "edits": {"count": 0, "total_size": 0},
                "snapshots": {"count": 0, "total_size": 0},
                "total_files": 0,
                "total_size": 0,
            }

            # Get clip stats
            clip_stats = (
                self.session.query(
                    func.count(Clip.id).label("count"),
                    func.coalesce(func.sum(Clip.file_size), 0).label("total_size"),
                )
                .filter(self.query_builder.build_user_filter(self.session, user_id, Clip))
                .first()
            )

            if clip_stats:
                stats["clips"]["count"] = clip_stats.count
                stats["clips"]["total_size"] = clip_stats.total_size

            # Get edit stats
            edit_stats = (
                self.session.query(
                    func.count(Edit.id).label("count"),
                    func.coalesce(func.sum(Edit.file_size), 0).label("total_size"),
                )
                .filter(self.query_builder.build_user_filter(self.session, user_id, Edit))
                .first()
            )

            if edit_stats:
                stats["edits"]["count"] = edit_stats.count
                stats["edits"]["total_size"] = edit_stats.total_size

            # Get snapshot stats
            snapshot_stats = (
                self.session.query(
                    func.count(Snapshot.id).label("count"),
                    func.coalesce(func.sum(Snapshot.file_size), 0).label("total_size"),
                )
                .filter(self.query_builder.build_user_filter(self.session, user_id, Snapshot))
                .first()
            )

            if snapshot_stats:
                stats["snapshots"]["count"] = snapshot_stats.count
                stats["snapshots"]["total_size"] = snapshot_stats.total_size

            # Calculate totals
            stats["total_files"] = (
                stats["clips"]["count"] + stats["edits"]["count"] + stats["snapshots"]["count"]
            )
            stats["total_size"] = (
                stats["clips"]["total_size"]
                + stats["edits"]["total_size"]
                + stats["snapshots"]["total_size"]
            )

            return stats

        except Exception as e:
            logger.error(f"Error getting storage stats for user {user_id}: {e}")
            return {
                "clips": {"count": 0, "total_size": 0},
                "edits": {"count": 0, "total_size": 0},
                "snapshots": {"count": 0, "total_size": 0},
                "total_files": 0,
                "total_size": 0,
                "error": str(e),
            }

    def get_old_files_for_cleanup(self, retention_days: int) -> List[Dict[str, Any]]:
        """Get files older than retention period for cleanup"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

            # Get old clips
            old_clips = self.session.query(Clip).filter(Clip.created_at < cutoff_date).all()

            # Get old edits
            old_edits = self.session.query(Edit).filter(Edit.created_at < cutoff_date).all()

            # Get old snapshots
            old_snapshots = (
                self.session.query(Snapshot).filter(Snapshot.created_at < cutoff_date).all()
            )

            old_files = []

            for clip in old_clips:
                old_files.append(
                    {
                        "type": "clip",
                        "id": clip.id,
                        "file_path": clip.file_path,
                        "created_at": clip.created_at,
                        "user_id": clip.user_id,
                    }
                )

            for edit in old_edits:
                old_files.append(
                    {
                        "type": "edit",
                        "id": edit.id,
                        "file_path": edit.file_path,
                        "created_at": edit.created_at,
                        "user_id": edit.user_id,
                    }
                )

            for snapshot in old_snapshots:
                old_files.append(
                    {
                        "type": "snapshot",
                        "id": snapshot.id,
                        "file_path": snapshot.file_path,
                        "created_at": snapshot.created_at,
                        "user_id": snapshot.user_id,
                    }
                )

            logger.info(f"Found {len(old_files)} files older than {retention_days} days")
            return old_files

        except Exception as e:
            logger.error(f"Error getting old files for cleanup: {e}")
            return []
