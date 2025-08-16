"""
Clip Processing Service - Service layer for video clip operations
Implements IClipProcessingService interface with proper error handling and logging
"""

import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ffmpeg  # type: ignore[import-untyped]
from core.config import settings
from core.exceptions import (
    ClipProcessingError,
    FileNotFoundError,
    MediaProcessingError,
    StorageError,
    ValidationError,
    VideoLimitExceededException,
)
from core.logging import get_logger, performance_logger
from core.resilience import FFMPEG_RETRY, retry_async
from domain.interfaces import IClipProcessingService
from domain.schemas import (
    ClipMetadata,
    ClipRequest,
    ClipResponse,
    EditRequest,
    EditResponse,
    FrameInfo,
    MultiFrameRequest,
    MultiFrameResponse,
    SessionInfo,
    SnapshotRequest,
    SnapshotResponse,
)
from infrastructure.database import get_db_session
from infrastructure.repositories import (
    ClipRepository,
    EditRepository,
    SnapshotRepository,
    StorageStatsRepository,
)


class TimeUtils:
    """Utility class for time calculations and conversions"""

    @staticmethod
    def parse_time_to_seconds(time_str: str) -> float:
        """Convert time string to seconds"""
        try:
            return float(time_str)
        except ValueError:
            parts = time_str.split(":")
            if len(parts) == 3:
                hours, minutes, seconds = parts
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            elif len(parts) == 2:
                minutes, seconds = parts
                return int(minutes) * 60 + float(seconds)
            else:
                raise ValidationError(f"Invalid time format: {time_str}")

    @staticmethod
    def seconds_to_time_string(seconds: float) -> str:
        """Convert seconds to HH:MM:SS format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    @staticmethod
    def calculate_duration(start_time: str, end_time: str) -> float:
        """Calculate duration between start and end times"""
        start_seconds = TimeUtils.parse_time_to_seconds(start_time)
        end_seconds = TimeUtils.parse_time_to_seconds(end_time)
        duration = end_seconds - start_seconds
        if duration <= 0:
            raise ValidationError("End time must be greater than start time")
        return duration


class ClipProcessingService(IClipProcessingService):
    """Service for processing video clips, snapshots and edits"""

    def __init__(self) -> None:
        self.clips_storage_path = settings.absolute_clips_path
        self.logger = get_logger("clip_processing")

        # Create subdirectories
        (self.clips_storage_path / "videos").mkdir(parents=True, exist_ok=True)
        (self.clips_storage_path / "snapshots").mkdir(parents=True, exist_ok=True)
        (self.clips_storage_path / "edited").mkdir(parents=True, exist_ok=True)
        (self.clips_storage_path / "thumbnails").mkdir(parents=True, exist_ok=True)

        # Test mode configuration (from settings, which loads .env file)
        self.test_mode = settings.test_mode
        self.test_video_file = settings.test_video_file

        # Log test mode configuration
        if self.test_mode:
            self.logger.info(f"Test mode ENABLED - using test video: {self.test_video_file}")
        else:
            self.logger.info("Test mode DISABLED - using Plex media files")

    async def _get_source_path(self, session: SessionInfo, plex_token: str) -> str:
        """Get the source file path, using test file if in test mode"""
        if self.test_mode:
            self.logger.info(f"Test mode active - looking for test video: {self.test_video_file}")
            possible_paths = [
                self.test_video_file if os.path.isabs(self.test_video_file) else None,
                self.test_video_file,
                os.path.join("..", self.test_video_file),
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    self.test_video_file,
                ),
            ]

            for path in possible_paths:
                if path and os.path.exists(path):
                    self.logger.info(f"Found test video at: {path}")
                    return os.path.abspath(path)
                elif path:
                    self.logger.debug(f"Test video not found at: {path}")

            self.logger.error(f"Test video file not found in any location: {self.test_video_file}")
            raise FileNotFoundError(f"Test video file not found: {self.test_video_file}")
        else:
            # Use Plex file path
            self.logger.info(f"Getting source path for media key: {session.media.key}")

            # Check if original_file_info is already available
            if hasattr(session, "original_file_info") and session.original_file_info:
                self.logger.info(
                    f"Using existing original_file_info: {session.original_file_info.file_path}"
                )
            else:
                self.logger.warning("original_file_info is not available, attempting to fetch it")

                # Try to get server context from session or create Plex service to fetch it
                server_context = getattr(session, "_server_context", None)

                if not server_context:
                    self.logger.warning(
                        "No server context available, attempting to get current session with context"
                    )
                    from services.plex_service import PlexService

                    plex_service = PlexService()

                    # Try to get the current session with server context
                    try:
                        current_session = await plex_service.get_current_session(
                            plex_token, session.username
                        )
                        if current_session and hasattr(current_session, "_server_context"):
                            server_context = getattr(current_session, "_server_context", None)
                            setattr(session, "_server_context", server_context)
                            self.logger.info(
                                "Successfully retrieved server context from current session"
                            )
                        else:
                            self.logger.warning(
                                "Could not retrieve server context from current session"
                            )
                    except Exception as e:
                        self.logger.error(f"Failed to get current session with context: {e}")

                if server_context and plex_token:
                    from core.config import settings
                    from services.plex_service import PlexService

                    plex_service = PlexService()

                    media_key = session.media.key
                    if media_key:
                        try:
                            self.logger.info(
                                f"Attempting to get media file info for key: {media_key}"
                            )

                            # Use server token if available for file access (admin privileges needed)
                            token_to_use = plex_token
                            self.logger.info(
                                f"Checking for server token: has_attr={hasattr(settings, 'plex_server_token')}, value={'set' if getattr(settings, 'plex_server_token', None) else 'not set'}"
                            )
                            if (
                                hasattr(settings, "plex_server_token")
                                and settings.plex_server_token
                            ):
                                self.logger.info(
                                    f"Using server token for file path access (token: {settings.plex_server_token[:5]}...{settings.plex_server_token[-5:]})"
                                )
                                token_to_use = settings.plex_server_token
                            else:
                                self.logger.info(
                                    f"Using user token for file path access (token: {plex_token[:5]}...{plex_token[-5:] if plex_token else 'None'})"
                                )

                            original_file_info = await plex_service.get_media_file_info(
                                token_to_use, server_context, media_key
                            )
                            session.original_file_info = original_file_info
                            self.logger.info(
                                f"Successfully retrieved file info: {original_file_info.file_path if original_file_info else 'None'}"
                            )
                        except Exception as e:
                            self.logger.error(f"Failed to get media file info: {e}")
                else:
                    self.logger.error(
                        f"Missing required parameters - server_context: {bool(server_context)}, plex_token: {bool(plex_token)}"
                    )

            # Check if we now have the file info
            if (
                hasattr(session, "original_file_info")
                and session.original_file_info
                and session.original_file_info.file_path
            ):
                file_path = session.original_file_info.file_path
                self.logger.info(f"Using file path: {file_path}")
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"Source file not found: {file_path}")
                return file_path

            # If we still don't have file info, provide more detailed error
            session_info_details = {
                "original_file_info": getattr(session, "original_file_info", "Not set"),
                "_server_context": bool(getattr(session, "_server_context", None)),
                "media_key": session.media.key,
                "username": session.username,
                "media_streams_count": (
                    len(session.media.media_streams)
                    if hasattr(session.media, "media_streams")
                    else 0
                ),
            }
            self.logger.error(
                f"No source file information available. Session details: {session_info_details}"
            )
            raise FileNotFoundError(
                "No source file information available. Unable to fetch file path from Plex server."
            )

    def _get_quality_settings(self, quality: str, is_snapshot: bool = False) -> Dict[str, Any]:
        """Get FFmpeg quality settings based on quality level"""
        settings_map: Dict[str, Dict[str, Any]]
        if is_snapshot:
            settings_map = {
                "low": {"qscale:v": 8},
                "medium": {"qscale:v": 4},
                "high": {"qscale:v": 2},
            }
        else:
            settings_map = {
                "low": {"crf": 28, "preset": "fast"},
                "medium": {"crf": 23, "preset": "medium"},
                "high": {"crf": 18, "preset": "slow"},
            }

        return settings_map.get(quality, settings_map["medium"])

    def _can_copy_streams(self, source_path: str, target_format: str) -> bool:
        """Check if we can copy streams without re-encoding for speed"""
        try:
            probe = ffmpeg.probe(source_path)
            video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
            audio_stream = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)

            if not video_stream:
                return False

            source_container = probe["format"]["format_name"].lower()
            video_codec = video_stream.get("codec_name", "").lower()
            audio_codec = audio_stream.get("codec_name", "") if audio_stream else ""

            if target_format == "mp4":
                return (
                    video_codec in ["h264", "x264"]
                    and audio_codec in ["aac", "mp3"]
                    and "mp4" in source_container
                )

            return False
        except Exception:
            return False

    def _generate_clip_title(self, session: SessionInfo) -> str:
        """Generate a meaningful title based on session information"""
        title = session.media.title or "Untitled"

        if session.media.show_title:
            if session.media.season_number and session.media.episode_number:
                title = f"{session.media.show_title} S{session.media.season_number:02d}E{session.media.episode_number:02d}"
                if session.media.title and session.media.title != "Unknown":
                    title += f" - {session.media.title}"
            else:
                title = session.media.show_title
                if session.media.title and session.media.title != "Unknown":
                    title += f" - {session.media.title}"
        elif not title or title == "Unknown":
            title = f"Clip {str(uuid.uuid4())[:8]}"

        return title

    async def create_clip(
        self,
        session: SessionInfo,
        request: ClipRequest,
        plex_token: str,
        user_id: str,
    ) -> ClipResponse:
        """Create a video clip from current session"""
        start_time = datetime.now()
        clip_id = str(uuid.uuid4())

        try:
            self.logger.info(
                f"Starting clip creation for user {user_id}", extra={"user_id": user_id}
            )

            # Check video limit before processing
            with get_db_session() as db_session:
                storage_repo = StorageStatsRepository(db_session)
                current_video_count = storage_repo.get_user_video_count(user_id)

                if current_video_count >= settings.user_video_limit:
                    raise VideoLimitExceededException(
                        f"Video limit exceeded. Maximum {settings.user_video_limit} videos allowed. "
                        f"Current count: {current_video_count}"
                    )

            # Get source path
            source_path = await self._get_source_path(session, plex_token)

            # Calculate timing and validate
            start_seconds = TimeUtils.parse_time_to_seconds(request.start_time)
            duration = TimeUtils.calculate_duration(request.start_time, request.end_time)

            # Generate output path
            filename = f"{clip_id}.{request.format}"
            output_path = self.clips_storage_path / "videos" / filename

            # Create metadata
            title = self._generate_clip_title(session)
            metadata = ClipMetadata(
                title=title,
                show_name=session.media.show_title,
                season_number=session.media.season_number,
                episode_number=session.media.episode_number,
                original_timestamp=TimeUtils.seconds_to_time_string(
                    session.session.view_offset / 1000
                ),
                username=session.username,
                duration=duration,
                created_at=datetime.now().isoformat() + "Z",
            )

            # Prepare FFmpeg command
            input_stream = ffmpeg.input(source_path, ss=start_seconds, t=duration)

            if self._can_copy_streams(source_path, request.format):
                output_args = {
                    "c": "copy",
                    "map_metadata": "-1",
                    "avoid_negative_ts": "make_zero",
                }
            else:
                quality_settings = self._get_quality_settings(request.quality)
                output_args = {
                    "vcodec": "libx264",
                    "acodec": "aac",
                    "pix_fmt": "yuv420p",
                    "map_metadata": "-1",
                    **quality_settings,
                }

            # Add metadata if requested
            if request.include_metadata:
                metadata_args = {
                    "metadata": f"title={metadata.title}",
                    "metadata:g:0": f"comment=Created at {metadata.original_timestamp} by {metadata.username}",
                }
                if metadata.show_name:
                    metadata_args["metadata:g:1"] = f"show={metadata.show_name}"
                if metadata.season_number:
                    metadata_args["metadata:g:2"] = f"season_number={metadata.season_number}"
                if metadata.episode_number:
                    metadata_args["metadata:g:3"] = f"episode_number={metadata.episode_number}"

                output_args.update(metadata_args)

            # Execute FFmpeg with retry logic
            output_stream = ffmpeg.output(input_stream, str(output_path), **output_args)

            def run_ffmpeg() -> None:
                try:
                    ffmpeg.run(
                        output_stream,
                        capture_stdout=True,
                        capture_stderr=True,
                        overwrite_output=True,
                    )
                except ffmpeg.Error as e:
                    stderr = e.stderr.decode("utf-8") if e.stderr else "No error details"
                    raise MediaProcessingError(f"FFmpeg error: {stderr}")

            loop = asyncio.get_event_loop()
            await retry_async(lambda: loop.run_in_executor(None, run_ffmpeg), strategy=FFMPEG_RETRY)

            # Wait for file to be fully written with retries
            # Initial wait to allow FFmpeg to finish writing
            await asyncio.sleep(1.0)  # 1 second initial wait

            max_retries = 50  # Increased retries
            file_ready = False
            last_size = 0
            stable_checks = 0
            minimum_file_size = 1024  # Minimum 1KB to ensure we don't catch partial writes

            for i in range(max_retries):
                await asyncio.sleep(0.3)  # 300ms wait each time

                if output_path.exists() or output_path.absolute().exists():
                    try:
                        current_size = (
                            output_path.stat().st_size
                            if output_path.exists()
                            else output_path.absolute().stat().st_size
                        )

                        # Check if file size is stable and above minimum threshold
                        if current_size >= minimum_file_size and current_size == last_size:
                            stable_checks += 1
                            if stable_checks >= 3:  # File size stable for 3 checks (900ms)
                                file_ready = True
                                self.logger.info(f"File ready, final size: {current_size} bytes")
                                break
                        else:
                            if current_size != last_size:
                                stable_checks = 0  # Reset if size changed

                        last_size = current_size
                    except OSError:
                        # File might be locked, continue waiting
                        pass

            if not file_ready:
                self.logger.warning(
                    f"File stability timeout after {max_retries} retries, last size: {last_size}"
                )
                # Continue anyway if file exists and has some content

            # Get file info
            try:
                # Try both relative and absolute paths
                if output_path.exists():
                    file_size = output_path.stat().st_size
                elif output_path.absolute().exists():
                    self.logger.warning(f"File found with absolute path: {output_path.absolute()}")
                    file_size = output_path.absolute().stat().st_size
                else:
                    # Try with os.path.exists as last resort
                    str_path = str(output_path)
                    if os.path.exists(str_path):
                        self.logger.warning(f"File found with os.path.exists: {str_path}")
                        file_size = os.path.getsize(str_path)
                    else:
                        self.logger.error(f"File does not exist after FFmpeg: {output_path}")
                        raise StorageError(f"Output file does not exist: {output_path}")
            except OSError as e:
                self.logger.error(f"OSError getting file size for {output_path}: {e}")
                raise StorageError(f"Failed to get file size: {e}")

            download_url = f"/api/v1/storage/video/{clip_id}"

            # Generate thumbnail from first frame
            thumbnail_url = None
            try:
                thumbnail_filename = f"thumb_{clip_id}.jpg"
                thumbnail_path = self.clips_storage_path / "thumbnails" / thumbnail_filename

                # Extract first frame (at 0 seconds) as thumbnail
                thumbnail_input = ffmpeg.input(str(output_path), ss=0)
                thumbnail_output = ffmpeg.output(
                    thumbnail_input,
                    str(thumbnail_path),
                    vframes=1,
                    s="320x180",  # Small thumbnail size
                    q=3,  # High quality JPEG
                )

                def run_thumbnail_ffmpeg() -> None:
                    try:
                        ffmpeg.run(
                            thumbnail_output,
                            capture_stdout=True,
                            capture_stderr=True,
                            overwrite_output=True,
                        )
                    except ffmpeg.Error as e:
                        # Log but don't fail clip creation if thumbnail fails
                        stderr = e.stderr.decode("utf-8") if e.stderr else "No error details"
                        self.logger.warning(
                            f"Thumbnail generation failed for clip {clip_id}: {stderr}"
                        )
                        raise

                # Generate thumbnail asynchronously
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, run_thumbnail_ffmpeg)

                # Check if thumbnail was created successfully
                if thumbnail_path.exists() and thumbnail_path.stat().st_size > 0:
                    thumbnail_url = f"/api/v1/storage/thumbnail/{clip_id}"
                    self.logger.info(f"Successfully generated thumbnail for clip {clip_id}")
                else:
                    self.logger.warning(f"Thumbnail file not found or empty for clip {clip_id}")

            except Exception as e:
                # Don't fail clip creation if thumbnail generation fails
                self.logger.warning(f"Failed to generate thumbnail for clip {clip_id}: {e}")

            # Store in database
            with get_db_session() as db:
                clip_repo = ClipRepository(db)
                clip_repo.create(
                    {
                        "id": clip_id,
                        "user_id": user_id,
                        "title": title,
                        "file_path": str(output_path),
                        "file_size": file_size,
                        "duration": duration,
                        "status": "completed",
                        "show_name": metadata.show_name,
                        "season_number": metadata.season_number,
                        "episode_number": metadata.episode_number,
                        "original_timestamp": metadata.original_timestamp,
                    }
                )

            # Log performance
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_logger.log_media_processing_duration(
                "clip_creation", file_size / (1024 * 1024), processing_time
            )

            self.logger.info(
                f"Successfully created clip {clip_id} for user {user_id}",
                extra={"user_id": user_id, "clip_id": clip_id},
            )

            return ClipResponse(
                clip_id=clip_id,
                status="completed",
                file_path=str(output_path),
                download_url=download_url,
                thumbnail_url=thumbnail_url,
                file_size=file_size,
                duration=duration,
                metadata=metadata,
                progress=100.0,
            )

        except (ValidationError, FileNotFoundError, MediaProcessingError, StorageError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error creating clip: {e}", extra={"user_id": user_id})
            raise ClipProcessingError(f"Clip creation failed: {str(e)}")

    async def delete_clip(self, clip_id: str, user_id: str) -> bool:
        """Delete a clip and its associated thumbnail"""
        try:
            self.logger.info(
                f"Deleting clip {clip_id} for user {user_id}",
                extra={"user_id": user_id, "clip_id": clip_id},
            )

            # First get the clip details from database
            with get_db_session() as db:
                clip_repo = ClipRepository(db)
                clip = clip_repo.get_by_id(clip_id, user_id)

                if not clip:
                    self.logger.warning(f"Clip {clip_id} not found for user {user_id}")
                    return False

                # Delete from database first
                if not clip_repo.delete_clip(clip_id, user_id):
                    self.logger.warning(f"Failed to delete clip {clip_id} from database")
                    return False

            # Then clean up files
            try:
                # Delete video file
                video_path = Path(clip.file_path)
                if video_path.exists():
                    video_path.unlink()
                    self.logger.info(f"Deleted video file: {video_path}")
                else:
                    self.logger.warning(f"Video file not found: {video_path}")

                # Delete thumbnail file
                thumbnail_filename = f"thumb_{clip_id}.jpg"
                thumbnail_path = self.clips_storage_path / "thumbnails" / thumbnail_filename
                if thumbnail_path.exists():
                    thumbnail_path.unlink()
                    self.logger.info(f"Deleted thumbnail file: {thumbnail_path}")
                else:
                    self.logger.debug(f"Thumbnail file not found: {thumbnail_path}")

            except Exception as e:
                # Log file deletion errors but don't fail the operation since DB is already updated
                self.logger.warning(f"Error cleaning up files for clip {clip_id}: {e}")

            self.logger.info(f"Successfully deleted clip {clip_id} for user {user_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error deleting clip {clip_id} for user {user_id}: {e}")
            return False

    async def bulk_delete_clips(self, clip_ids: List[str], user_id: str) -> Tuple[int, List[str]]:
        """Delete multiple clips and their thumbnails"""
        deleted_count = 0
        failed_clips = []

        self.logger.info(
            f"Bulk deleting {len(clip_ids)} clips for user {user_id}",
            extra={"user_id": user_id, "clip_count": len(clip_ids)},
        )

        for clip_id in clip_ids:
            try:
                if await self.delete_clip(clip_id, user_id):
                    deleted_count += 1
                else:
                    failed_clips.append(clip_id)
            except Exception as e:
                self.logger.error(f"Failed to delete clip {clip_id}: {e}")
                failed_clips.append(clip_id)

        self.logger.info(f"Bulk delete completed: {deleted_count}/{len(clip_ids)} clips deleted")
        return deleted_count, failed_clips

    async def create_snapshot(
        self,
        session: SessionInfo,
        request: SnapshotRequest,
        plex_token: str,
        user_id: str,
    ) -> SnapshotResponse:
        """Create a snapshot from current session"""
        start_time = datetime.now()
        snapshot_id = str(uuid.uuid4())

        try:
            self.logger.info(
                f"Starting snapshot creation for user {user_id}",
                extra={"user_id": user_id},
            )

            # Get source path
            source_path = await self._get_source_path(session, plex_token)

            # Calculate timing
            timestamp_seconds = TimeUtils.parse_time_to_seconds(request.timestamp)

            # Generate output path
            filename = f"{snapshot_id}.{request.format}"
            output_path = self.clips_storage_path / "snapshots" / filename

            # Prepare FFmpeg command
            quality_settings = self._get_quality_settings(request.quality, is_snapshot=True)

            input_stream = ffmpeg.input(source_path, ss=timestamp_seconds)
            output_stream = ffmpeg.output(
                input_stream, str(output_path), vframes=1, **quality_settings
            )

            # Execute FFmpeg with retry logic
            def run_ffmpeg() -> None:
                try:
                    ffmpeg.run(
                        output_stream,
                        capture_stdout=True,
                        capture_stderr=True,
                        overwrite_output=True,
                    )
                except ffmpeg.Error as e:
                    stderr = e.stderr.decode("utf-8") if e.stderr else "No error details"
                    raise MediaProcessingError(f"FFmpeg error: {stderr}")

            loop = asyncio.get_event_loop()
            await retry_async(lambda: loop.run_in_executor(None, run_ffmpeg), strategy=FFMPEG_RETRY)

            # Add delay and retry to ensure file is written to disk
            file_exists = False
            max_retries = 10
            for retry_count in range(max_retries):
                await asyncio.sleep(0.05)  # Wait 50ms between checks
                if output_path.exists():
                    file_exists = True
                    break

            # Get file info
            try:
                if not file_exists:
                    raise StorageError(
                        f"Output file does not exist after FFmpeg with {max_retries} retries: {output_path}"
                    )
                file_size = output_path.stat().st_size
            except OSError as e:
                raise StorageError(f"Failed to get file size: {e}")

            download_url = f"/api/v1/storage/snapshot/{snapshot_id}"

            # Store in database
            with get_db_session() as db:
                snapshot_repo = SnapshotRepository(db)
                snapshot_repo.create(
                    {
                        "id": snapshot_id,
                        "user_id": user_id,
                        "file_path": str(output_path),
                        "file_size": file_size,
                        "timestamp": request.timestamp,
                        "status": "completed",
                    }
                )

            # Log performance
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_logger.log_media_processing_duration(
                "snapshot_creation", file_size / (1024 * 1024), processing_time
            )

            self.logger.info(
                f"Successfully created snapshot {snapshot_id} for user {user_id}",
                extra={"user_id": user_id, "snapshot_id": snapshot_id},
            )

            return SnapshotResponse(
                snapshot_id=snapshot_id,
                status="completed",
                file_path=str(output_path),
                download_url=download_url,
                file_size=file_size,
                timestamp=request.timestamp,
            )

        except (ValidationError, FileNotFoundError, MediaProcessingError, StorageError):
            raise
        except Exception as e:
            self.logger.error(
                f"Unexpected error creating snapshot: {e}", extra={"user_id": user_id}
            )
            raise ClipProcessingError(f"Snapshot creation failed: {str(e)}")

    async def create_multi_frame_snapshots(
        self,
        session: SessionInfo,
        request: MultiFrameRequest,
        plex_token: str,
        user_id: str,
    ) -> MultiFrameResponse:
        """Create multiple frames around a center timestamp"""
        start_time = datetime.now()

        try:
            self.logger.info(
                f"Starting multi-frame creation for user {user_id}",
                extra={"user_id": user_id},
            )

            # Get source path
            source_path = await self._get_source_path(session, plex_token)

            # Get video frame rate
            try:
                probe = ffmpeg.probe(source_path)
                video_stream = next(
                    (s for s in probe["streams"] if s["codec_type"] == "video"), None
                )
                if not video_stream:
                    raise MediaProcessingError("No video stream found in source file")

                fps_str = video_stream.get("r_frame_rate", "30/1")
                if "/" in fps_str:
                    num, den = fps_str.split("/")
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)

                if fps <= 0:
                    fps = 30.0

            except Exception as e:
                self.logger.warning(f"Could not determine frame rate, using default 30fps: {e}")
                fps = 30.0

            # Calculate frame numbers
            center_timestamp_seconds = TimeUtils.parse_time_to_seconds(request.center_timestamp)
            center_frame_number = int(center_timestamp_seconds * fps)

            frame_numbers = []
            for i in range(-request.frame_count_before, request.frame_count_after + 1):
                frame_number = center_frame_number + i
                if frame_number >= 0:
                    frame_numbers.append(frame_number)

            frames = []
            quality_settings = self._get_quality_settings(request.quality, is_snapshot=True)

            # Extract each frame
            self.logger.info(
                f"Attempting to extract {len(frame_numbers)} frames",
                extra={"user_id": user_id},
            )
            for frame_number in frame_numbers:
                frame_id = str(uuid.uuid4())

                timestamp = frame_number / fps
                filename = f"frame_{frame_id}.{request.format}"
                output_path = self.clips_storage_path / "snapshots" / filename

                try:
                    input_stream = ffmpeg.input(source_path, ss=timestamp)
                    output_stream = ffmpeg.output(
                        input_stream, str(output_path), vframes=1, **quality_settings
                    )

                    def run_ffmpeg() -> None:
                        try:
                            ffmpeg.run(
                                output_stream,
                                capture_stdout=True,
                                capture_stderr=True,
                                overwrite_output=True,
                            )
                        except ffmpeg.Error as e:
                            stderr = e.stderr.decode("utf-8") if e.stderr else "No error details"
                            raise MediaProcessingError(f"FFmpeg error: {stderr}")

                    loop = asyncio.get_event_loop()
                    await retry_async(
                        lambda: loop.run_in_executor(None, run_ffmpeg),
                        strategy=FFMPEG_RETRY,
                    )

                    # Add delay and retry to ensure file is written to disk
                    file_exists = False
                    max_retries = 10
                    for retry_count in range(max_retries):
                        await asyncio.sleep(0.05)  # Wait 50ms between checks
                        if output_path.exists():
                            file_exists = True
                            break

                    if not file_exists:
                        self.logger.warning(
                            f"Output file does not exist after FFmpeg with {max_retries} retries: {output_path}"
                        )
                        continue

                    file_size = output_path.stat().st_size
                    download_url = f"/api/v1/storage/snapshot/{frame_id}"

                    frames.append(
                        FrameInfo(
                            frame_id=frame_id,
                            timestamp=TimeUtils.seconds_to_time_string(timestamp),
                            download_url=download_url,
                            file_path=str(output_path),
                            file_size=file_size,
                        )
                    )

                    self.logger.debug(
                        f"Successfully extracted frame {frame_number} at timestamp {timestamp}",
                        extra={"user_id": user_id, "frame_id": frame_id},
                    )

                    # Store in database
                    with get_db_session() as db:
                        snapshot_repo = SnapshotRepository(db)
                        snapshot_repo.create(
                            {
                                "id": frame_id,
                                "user_id": user_id,
                                "file_path": str(output_path),
                                "file_size": file_size,
                                "timestamp": TimeUtils.seconds_to_time_string(timestamp),
                                "status": "completed",
                            }
                        )

                except (ffmpeg.Error, MediaProcessingError, OSError) as e:
                    self.logger.warning(f"Error extracting frame {frame_number}: {e}")
                    continue
                except Exception as e:
                    self.logger.error(f"Unexpected error extracting frame {frame_number}: {e}")
                    continue

            if not frames:
                error_msg = f"Failed to extract any frames from {len(frame_numbers)} attempted frames. Source: {source_path}, Center timestamp: {request.center_timestamp}"
                self.logger.error(error_msg, extra={"user_id": user_id, "source_path": source_path})
                raise MediaProcessingError(error_msg)

            # Log performance
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            total_size = sum(frame.file_size for frame in frames) / (1024 * 1024)
            performance_logger.log_media_processing_duration(
                "multi_frame_creation", total_size, processing_time
            )

            self.logger.info(
                f"Successfully created {len(frames)} frames for user {user_id}",
                extra={"user_id": user_id, "frame_count": len(frames)},
            )

            # Convert FrameInfo objects to dictionaries for the response schema
            frames_data = []
            for frame in frames:
                frames_data.append(
                    {
                        "frame_id": frame.frame_id,
                        "timestamp": frame.timestamp,
                        "download_url": frame.download_url,
                        "file_path": frame.file_path,
                        "file_size": str(frame.file_size),
                    }
                )

            return MultiFrameResponse(status="completed", frames=frames_data)

        except (ValidationError, FileNotFoundError, MediaProcessingError, StorageError):
            raise
        except Exception as e:
            self.logger.error(
                f"Unexpected error creating multi-frame: {e}",
                extra={"user_id": user_id},
            )
            raise ClipProcessingError(f"Multi-frame creation failed: {str(e)}")

    async def edit_clip(
        self, source_clip_id: str, request: EditRequest, user_id: str
    ) -> EditResponse:
        """Edit an existing clip by trimming it"""
        start_time = datetime.now()
        edit_id = str(uuid.uuid4())

        try:
            self.logger.info(f"Starting clip edit for user {user_id}", extra={"user_id": user_id})

            # Check video limit before processing
            with get_db_session() as db_session:
                storage_repo = StorageStatsRepository(db_session)
                current_video_count = storage_repo.get_user_video_count(user_id)

                if current_video_count >= settings.user_video_limit:
                    raise VideoLimitExceededException(
                        f"Video limit exceeded. Maximum {settings.user_video_limit} videos allowed. "
                        f"Current count: {current_video_count}"
                    )

            # Get source clip
            with get_db_session() as db:
                clip_repo = ClipRepository(db)
                clip = clip_repo.get_by_id(source_clip_id, user_id)

                if not clip:
                    raise FileNotFoundError("Source clip not found or access denied")

                source_clip_path = str(clip.file_path)

            if not os.path.exists(source_clip_path):
                raise FileNotFoundError(f"Source clip file not found: {source_clip_path}")

            # Calculate timing and validate
            start_seconds = TimeUtils.parse_time_to_seconds(request.start_time)
            duration = TimeUtils.calculate_duration(request.start_time, request.end_time)

            # Generate output path
            filename = f"{edit_id}.{request.format}"
            output_path = self.clips_storage_path / "edited" / filename

            # Prepare FFmpeg command
            input_stream = ffmpeg.input(source_clip_path, ss=start_seconds, t=duration)

            if self._can_copy_streams(source_clip_path, request.format):
                output_args = {
                    "c": "copy",
                    "map_metadata": "-1",
                    "avoid_negative_ts": "make_zero",
                }
            else:
                quality_settings = self._get_quality_settings(request.quality)
                output_args = {
                    "vcodec": "libx264",
                    "acodec": "aac",
                    "pix_fmt": "yuv420p",
                    "map_metadata": "-1",
                    **quality_settings,
                }

            # Execute FFmpeg with retry logic
            output_stream = ffmpeg.output(input_stream, str(output_path), **output_args)

            def run_ffmpeg() -> None:
                try:
                    ffmpeg.run(
                        output_stream,
                        capture_stdout=True,
                        capture_stderr=True,
                        overwrite_output=True,
                    )
                except ffmpeg.Error as e:
                    stderr = e.stderr.decode("utf-8") if e.stderr else "No error details"
                    raise MediaProcessingError(f"FFmpeg error: {stderr}")

            loop = asyncio.get_event_loop()
            await retry_async(lambda: loop.run_in_executor(None, run_ffmpeg), strategy=FFMPEG_RETRY)

            # Wait for file to be fully written with retries
            max_retries = 30
            last_size = 0
            stable_checks = 0

            for i in range(max_retries):
                await asyncio.sleep(0.2)  # 200ms wait each time

                if output_path.exists() or output_path.absolute().exists():
                    try:
                        current_size = (
                            output_path.stat().st_size
                            if output_path.exists()
                            else output_path.absolute().stat().st_size
                        )

                        # Check if file size is stable (not being written to)
                        if current_size > 0 and current_size == last_size:
                            stable_checks += 1
                            if stable_checks >= 2:  # File size stable for 2 checks
                                self.logger.info(
                                    f"File ready after {i+1} retries, size: {current_size}"
                                )
                                break
                        else:
                            stable_checks = 0

                        last_size = current_size
                        self.logger.debug(
                            f"File size: {current_size}, stable checks: {stable_checks}"
                        )
                    except OSError:
                        # File might be locked, continue waiting
                        pass

                self.logger.debug(f"File not ready, retry {i+1}/{max_retries}: {output_path}")

            # Get file info
            try:
                self.logger.info(f"Checking file size for: {output_path}")
                self.logger.info(f"File exists: {output_path.exists()}")
                # Try both relative and absolute paths
                if output_path.exists():
                    file_size = output_path.stat().st_size
                    self.logger.info(f"File size: {file_size}")
                elif output_path.absolute().exists():
                    self.logger.warning(f"File found with absolute path: {output_path.absolute()}")
                    file_size = output_path.absolute().stat().st_size
                    self.logger.info(f"File size: {file_size}")
                else:
                    # Try with os.path.exists as last resort
                    str_path = str(output_path)
                    if os.path.exists(str_path):
                        self.logger.warning(f"File found with os.path.exists: {str_path}")
                        file_size = os.path.getsize(str_path)
                        self.logger.info(f"File size: {file_size}")
                    else:
                        self.logger.error(f"File does not exist after FFmpeg: {output_path}")
                        self.logger.error(f"Absolute path: {output_path.absolute()}")
                        self.logger.error(f"String path: {str_path}")
                        raise StorageError(f"Output file does not exist: {output_path}")
            except OSError as e:
                self.logger.error(f"OSError getting file size for {output_path}: {e}")
                raise StorageError(f"Failed to get file size: {e}")

            download_url = f"/api/v1/storage/edit/{edit_id}"

            # Create metadata
            metadata = ClipMetadata(
                title=f"Edited Clip {edit_id[:8]}",
                show_name=None,
                season_number=None,
                episode_number=None,
                original_timestamp="",
                username="",
                duration=duration,
                created_at=datetime.now().isoformat() + "Z",
            )

            # Store in database
            with get_db_session() as db:
                edit_repo = EditRepository(db)
                edit_repo.create(
                    {
                        "id": edit_id,
                        "user_id": user_id,
                        "source_clip_id": source_clip_id,
                        "file_path": str(output_path),
                        "file_size": file_size,
                        "duration": duration,
                        "start_time": request.start_time,
                        "end_time": request.end_time,
                        "quality": request.quality,
                        "format": request.format,
                        "status": "completed",
                    }
                )

            # Log performance
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            performance_logger.log_media_processing_duration(
                "clip_edit", file_size / (1024 * 1024), processing_time
            )

            self.logger.info(
                f"Successfully edited clip {edit_id} for user {user_id}",
                extra={"user_id": user_id, "edit_id": edit_id},
            )

            return EditResponse(
                edit_id=edit_id,
                source_clip_id=source_clip_id,
                status="completed",
                file_path=str(output_path),
                download_url=download_url,
                file_size=file_size,
                duration=duration,
                metadata=metadata,
                progress=100.0,
            )

        except (ValidationError, FileNotFoundError, MediaProcessingError, StorageError):
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error editing clip: {e}", extra={"user_id": user_id})
            raise ClipProcessingError(f"Clip edit failed: {str(e)}")

    async def generate_preview_frames(
        self,
        session: SessionInfo,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        plex_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate preview frames at start and end times"""
        try:
            # Get source path
            if plex_token is None:
                raise ValidationError("Plex token is required for preview frame generation")
            source_path = await self._get_source_path(session, plex_token)

            frames = {}
            quality_settings = self._get_quality_settings("medium", is_snapshot=True)

            # Generate start frame if requested
            if start_time:
                start_seconds = TimeUtils.parse_time_to_seconds(start_time)
                start_frame_id = str(uuid.uuid4())
                filename = f"preview_start_{start_frame_id}.jpg"
                output_path = self.clips_storage_path / "snapshots" / filename

                input_stream = ffmpeg.input(source_path, ss=start_seconds)
                output_stream = ffmpeg.output(
                    input_stream, str(output_path), vframes=1, **quality_settings
                )

                def run_ffmpeg() -> None:
                    try:
                        ffmpeg.run(output_stream, capture_stdout=True, capture_stderr=True)
                    except ffmpeg.Error as e:
                        stderr = e.stderr.decode("utf-8") if e.stderr else "No error details"
                        raise MediaProcessingError(f"FFmpeg error: {stderr}")

                async def run_ffmpeg_and_verify() -> None:
                    """Run FFmpeg and verify the output file was created"""
                    # Run FFmpeg
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, run_ffmpeg)

                    # Wait a moment for filesystem sync
                    await asyncio.sleep(0.1)

                    # Verify file was created
                    if not output_path.exists():
                        raise StorageError(f"Preview start frame was not created: {output_path}")

                await retry_async(
                    run_ffmpeg_and_verify,
                    strategy=FFMPEG_RETRY,
                )

                try:
                    file_size = output_path.stat().st_size
                except OSError as e:
                    raise StorageError(f"Failed to get file size: {e}")

                # Store preview frame in database temporarily for cleanup
                if user_id:
                    with get_db_session() as db:
                        snapshot_repo = SnapshotRepository(db)
                        snapshot_repo.create(
                            {
                                "id": start_frame_id,
                                "user_id": user_id,
                                "file_path": str(output_path),
                                "file_size": file_size,
                                "timestamp": start_time,
                                "status": "completed",
                            }
                        )

                frames["start_frame"] = {
                    "frame_id": start_frame_id,
                    "timestamp": start_time,
                    "download_url": f"/api/v1/storage/snapshot/{start_frame_id}",
                    "file_path": str(output_path),
                }

            # Generate end frame if requested
            if end_time:
                end_seconds = TimeUtils.parse_time_to_seconds(end_time)
                end_frame_id = str(uuid.uuid4())
                filename = f"preview_end_{end_frame_id}.jpg"
                output_path = self.clips_storage_path / "snapshots" / filename

                input_stream = ffmpeg.input(source_path, ss=end_seconds)
                output_stream = ffmpeg.output(
                    input_stream, str(output_path), vframes=1, **quality_settings
                )

                def run_ffmpeg_end() -> None:
                    try:
                        ffmpeg.run(output_stream, capture_stdout=True, capture_stderr=True)
                    except ffmpeg.Error as e:
                        stderr = e.stderr.decode("utf-8") if e.stderr else "No error details"
                        raise MediaProcessingError(f"FFmpeg error: {stderr}")

                async def run_ffmpeg_and_verify_end() -> None:
                    """Run FFmpeg and verify the output file was created"""
                    # Run FFmpeg
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, run_ffmpeg_end)

                    # Wait a moment for filesystem sync
                    await asyncio.sleep(0.1)

                    # Verify file was created
                    if not output_path.exists():
                        raise StorageError(f"Preview end frame was not created: {output_path}")

                await retry_async(
                    run_ffmpeg_and_verify_end,
                    strategy=FFMPEG_RETRY,
                )

                try:
                    file_size = output_path.stat().st_size
                except OSError as e:
                    raise StorageError(f"Failed to get file size: {e}")

                # Store preview frame in database temporarily for cleanup
                if user_id:
                    with get_db_session() as db:
                        snapshot_repo = SnapshotRepository(db)
                        snapshot_repo.create(
                            {
                                "id": end_frame_id,
                                "user_id": user_id,
                                "file_path": str(output_path),
                                "file_size": file_size,
                                "timestamp": end_time,
                                "status": "completed",
                            }
                        )

                frames["end_frame"] = {
                    "frame_id": end_frame_id,
                    "timestamp": end_time,
                    "download_url": f"/api/v1/storage/snapshot/{end_frame_id}",
                    "file_path": str(output_path),
                }

            return {"status": "completed", "frames": frames}

        except Exception as e:
            self.logger.error(f"Failed to generate preview frames: {e}")
            return {
                "status": "failed",
                "error_message": f"Preview frame generation failed: {str(e)}",
            }

    async def cleanup_snapshot_frames(self, frame_ids: List[str], user_id: str) -> Dict[str, Any]:
        """Clean up snapshot frames by frame IDs"""
        try:
            self.logger.info(
                f"Starting cleanup of {len(frame_ids)} snapshot frames for user {user_id}",
                extra={"user_id": user_id, "frame_count": len(frame_ids)},
            )

            cleaned_count = 0
            errors = []

            with get_db_session() as db:
                snapshot_repo = SnapshotRepository(db)

                for frame_id in frame_ids:
                    try:
                        # Get snapshot from database
                        snapshot = snapshot_repo.get_by_id(frame_id, user_id)

                        if snapshot:
                            # Delete the file if it exists
                            if snapshot.file_path and os.path.exists(snapshot.file_path):
                                os.remove(snapshot.file_path)
                                self.logger.debug(f"Deleted snapshot file: {snapshot.file_path}")

                            # Remove from database
                            snapshot_repo.delete(frame_id, user_id)
                            cleaned_count += 1

                            self.logger.debug(f"Cleaned up snapshot frame {frame_id}")
                        else:
                            self.logger.warning(
                                f"Snapshot frame {frame_id} not found or access denied"
                            )
                            errors.append(f"Frame {frame_id} not found or access denied")

                    except Exception as e:
                        error_msg = f"Failed to cleanup frame {frame_id}: {str(e)}"
                        self.logger.error(error_msg)
                        errors.append(error_msg)

            self.logger.info(
                f"Cleaned up {cleaned_count} snapshot frames for user {user_id}",
                extra={"user_id": user_id, "cleaned_count": cleaned_count},
            )

            return {"cleaned_count": cleaned_count, "errors": errors}

        except Exception as e:
            self.logger.error(
                f"Failed to cleanup snapshot frames for user {user_id}: {e}",
                extra={"user_id": user_id},
            )
            raise ClipProcessingError(f"Snapshot cleanup failed: {str(e)}")
