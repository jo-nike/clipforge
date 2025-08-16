"""
Clips API Endpoints - FastAPI routes for clip management
Implements secure clip operations with proper service layer separation
"""

from datetime import datetime
from typing import Any, Dict, Tuple

from api.dependencies import (
    get_authenticated_user,
    get_authenticated_user_with_plex_token,
    get_clip_processing_service,
    get_plex_service,
    handle_service_error,
    setup_request_context,
    validate_pagination,
)
from core.audit import log_clip_bulk_delete, log_clip_create, log_clip_delete
from core.exceptions import ClipForgeException, SessionNotFoundError, VideoLimitExceededException
from core.logging import get_logger
from domain.schemas import (
    BulkDeleteRequest,
    ClipListResponse,
    ClipMetadata,
    ClipMetadataUpdate,
    ClipRequest,
    ClipResponse,
    EditRequest,
    EditResponse,
    PlexUser,
)
from fastapi import APIRouter, Depends, HTTPException, status
from infrastructure.database import get_db_session
from infrastructure.repositories import ClipRepository, EditRepository
from services.clip_service import ClipProcessingService
from services.plex_service import PlexService

logger = get_logger("clips_api")
router = APIRouter(prefix="/clips", tags=["Clips"])


@router.post("/create", response_model=ClipResponse)
async def create_clip(
    request: ClipRequest,
    _: str = Depends(setup_request_context),
    user_and_token: Tuple = Depends(get_authenticated_user_with_plex_token),
    clip_service: ClipProcessingService = Depends(get_clip_processing_service),
    plex_service: PlexService = Depends(get_plex_service),
) -> ClipResponse:
    """Create a video clip from current session (protected endpoint)"""
    current_user, plex_token = user_and_token

    try:
        logger.info(
            f"Creating clip for user {current_user.username}",
            extra={"user_id": current_user.user_id},
        )

        # Get user's current session
        session = await plex_service.get_current_session(plex_token, current_user.username)

        if not session:
            logger.warning(f"No active session found for user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active playback session found",
            )

        # Create the clip using the service
        clip_response = await clip_service.create_clip(
            session, request, plex_token, current_user.user_id
        )

        logger.info(
            f"Successfully created clip {clip_response.clip_id} for user {current_user.username}",
            extra={"user_id": current_user.user_id, "clip_id": clip_response.clip_id},
        )

        # Audit log clip creation
        log_clip_create(
            user_id=current_user.user_id,
            username=current_user.username,
            clip_id=clip_response.clip_id or "unknown",
            details={
                "title": request.title,
                "start_time": request.start_time,
                "end_time": request.end_time,
                "quality": request.quality,
                "format": request.format,
            },
        )

        return clip_response

    except HTTPException:
        raise
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except VideoLimitExceededException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to create clip for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create clip: {str(e)}",
        )


@router.get("/list", response_model=ClipListResponse)
async def list_user_clips(
    pagination: Dict[str, int] = Depends(validate_pagination),
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> ClipListResponse:
    """List user's clips with secure pagination (protected endpoint)"""
    try:
        logger.debug(
            f"Listing clips for user {current_user.username}",
            extra={"user_id": current_user.user_id},
        )

        with get_db_session() as db:
            clip_repo = ClipRepository(db)

            clips, total_count = clip_repo.list_user_clips(
                current_user.user_id, pagination["offset"], pagination["page_size"]
            )

            # Convert to ClipResponse format with metadata
            clips_data = []
            for clip in clips:
                # Check if thumbnail exists for this clip
                from pathlib import Path

                from core.config import settings

                thumbnail_filename = f"thumb_{clip.id}.jpg"
                thumbnail_path = (
                    Path(settings.absolute_clips_path) / "thumbnails" / thumbnail_filename
                )
                thumbnail_url = (
                    f"/api/v1/storage/thumbnail/{clip.id}" if thumbnail_path.exists() else None
                )

                clip_response = ClipResponse(
                    clip_id=clip.id,
                    status=clip.status,
                    file_path=clip.file_path,
                    download_url=f"/api/v1/storage/video/{clip.id}",
                    thumbnail_url=thumbnail_url,
                    file_size=clip.file_size,
                    duration=clip.duration,
                    created_at=clip.created_at.isoformat() + "Z" if clip.created_at else None,
                )

                # Add metadata that frontend expects
                clip_response.metadata = ClipMetadata(
                    title=clip.title or "Unknown",
                    show_name=clip.show_name,
                    season_number=clip.season_number,
                    episode_number=clip.episode_number,
                    original_timestamp=clip.original_timestamp or "00:00:00",
                    username="",  # Username not stored in clip table
                    duration=float(clip.duration or 0),
                    created_at=(clip.created_at or datetime.now()).isoformat() + "Z",
                )

                clips_data.append(clip_response)

        logger.debug(
            f"Retrieved {len(clips_data)} clips for user {current_user.username}",
            extra={"user_id": current_user.user_id, "clip_count": len(clips_data)},
        )

        return ClipListResponse(
            clips=clips_data,
            total_count=total_count,
            page=pagination["page"],
            page_size=pagination["page_size"],
        )

    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Error listing clips for user {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading clips: {str(e)}",
        )


@router.get("/{clip_id}", response_model=ClipResponse)
async def get_clip(
    clip_id: str,
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> ClipResponse:
    """Get clip information by ID (protected endpoint)"""
    try:
        logger.debug(
            f"Getting clip {clip_id} for user {current_user.username}",
            extra={"user_id": current_user.user_id, "clip_id": clip_id},
        )

        with get_db_session() as db:
            clip_repo = ClipRepository(db)
            clip = clip_repo.get_by_id(clip_id, current_user.user_id)

            if not clip:
                logger.warning(
                    f"Clip {clip_id} not found for user {current_user.username}",
                    extra={"user_id": current_user.user_id, "clip_id": clip_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Clip not found or access denied",
                )

            return ClipResponse(
                status=clip.status,
                clip_id=clip.id,
                file_path=clip.file_path,
                download_url=f"/api/v1/storage/video/{clip.id}",
                file_size=clip.file_size,
                duration=clip.duration,
                created_at=clip.created_at.isoformat() + "Z" if clip.created_at else None,
            )

    except HTTPException:
        raise
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Error getting clip {clip_id} for user {current_user.username}: {e}",
            extra={"user_id": current_user.user_id, "clip_id": clip_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve clip",
        )


@router.put("/{clip_id}/metadata")
async def update_clip_metadata(
    clip_id: str,
    update_data: ClipMetadataUpdate,
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Update clip metadata (protected endpoint)"""
    try:
        logger.info(
            f"Updating metadata for clip {clip_id} for user {current_user.username}",
            extra={"user_id": current_user.user_id, "clip_id": clip_id},
        )

        with get_db_session() as db:
            clip_repo = ClipRepository(db)

            # Check if clip exists and user owns it
            clip = clip_repo.get_by_id(clip_id, current_user.user_id)
            if not clip:
                logger.warning(
                    f"Clip {clip_id} not found for metadata update",
                    extra={"user_id": current_user.user_id, "clip_id": clip_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Clip not found or access denied",
                )

            # Update the metadata
            if clip_repo.update_metadata(
                clip_id, current_user.user_id, {"title": update_data.title}
            ):
                logger.info(
                    f"Updated clip {clip_id} metadata for user {current_user.username}",
                    extra={"user_id": current_user.user_id, "clip_id": clip_id},
                )
                return {
                    "status": "success",
                    "message": "Clip metadata updated successfully",
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update clip metadata",
                )

    except HTTPException:
        raise
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Error updating clip {clip_id} metadata for user {current_user.username}: {e}",
            extra={"user_id": current_user.user_id, "clip_id": clip_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update clip metadata",
        )


@router.post("/edit", response_model=EditResponse)
async def edit_clip(
    request: EditRequest,
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
    clip_service: ClipProcessingService = Depends(get_clip_processing_service),
) -> EditResponse:
    """Edit an existing clip by trimming it (protected endpoint)"""
    try:
        logger.info(
            f"Editing clip {request.source_clip_id} for user {current_user.username}",
            extra={
                "user_id": current_user.user_id,
                "source_clip_id": request.source_clip_id,
            },
        )

        # Use the service to edit the clip
        edit_response = await clip_service.edit_clip(
            request.source_clip_id, request, current_user.user_id
        )

        logger.info(
            f"Successfully created edit {edit_response.edit_id} for user {current_user.username}",
            extra={"user_id": current_user.user_id, "edit_id": edit_response.edit_id},
        )

        return edit_response

    except VideoLimitExceededException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to edit clip for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit clip: {str(e)}",
        )


@router.get("/{clip_id}/edited")
async def get_edited_videos(
    clip_id: str,
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Get all edited videos from a source clip (protected endpoint)"""
    try:
        logger.debug(
            f"Getting edited videos for clip {clip_id} for user {current_user.username}",
            extra={"user_id": current_user.user_id, "clip_id": clip_id},
        )

        with get_db_session() as db:
            clip_repo = ClipRepository(db)
            edit_repo = EditRepository(db)

            # Check if source clip exists and user owns it
            clip = clip_repo.get_by_id(clip_id, current_user.user_id)
            if not clip:
                logger.warning(
                    f"Source clip {clip_id} not found for edited videos query",
                    extra={"user_id": current_user.user_id, "clip_id": clip_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Source clip not found or access denied",
                )

            # Get edited videos for this user
            edited_videos = edit_repo.get_edits_by_source_clip(clip_id, current_user.user_id)

            # Convert to response format
            edited_response = []
            for edit in edited_videos:
                edited_response.append(
                    {
                        "edit_id": edit.id,
                        "file_path": edit.file_path,
                        "download_url": f"/api/v1/storage/edit/{edit.id}",
                        "file_size": edit.file_size,
                        "duration": edit.duration,
                        "start_time": edit.start_time,
                        "end_time": edit.end_time,
                        "quality": edit.quality,
                        "format": edit.format,
                        "status": edit.status,
                        "created_at": (
                            edit.created_at.isoformat() + "Z" if edit.created_at else None
                        ),
                    }
                )

            logger.debug(
                f"Found {len(edited_response)} edited videos for clip {clip_id}",
                extra={
                    "user_id": current_user.user_id,
                    "clip_id": clip_id,
                    "edit_count": len(edited_response),
                },
            )

            return {
                "source_clip_id": clip_id,
                "edited_videos": edited_response,
                "count": len(edited_response),
            }

    except HTTPException:
        raise
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Error getting edited videos for clip {clip_id}: {e}",
            extra={"user_id": current_user.user_id, "clip_id": clip_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get edited videos",
        )


@router.delete("/{clip_id}")
async def delete_clip(
    clip_id: str,
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
    clip_service: ClipProcessingService = Depends(get_clip_processing_service),
) -> Dict[str, Any]:
    """Delete a clip (protected endpoint)"""
    try:
        logger.info(
            f"Deleting clip {clip_id} for user {current_user.username}",
            extra={"user_id": current_user.user_id, "clip_id": clip_id},
        )

        if await clip_service.delete_clip(clip_id, current_user.user_id):
            logger.info(
                f"Successfully deleted clip {clip_id} for user {current_user.username}",
                extra={"user_id": current_user.user_id, "clip_id": clip_id},
            )

            # Audit log clip deletion
            log_clip_delete(
                user_id=current_user.user_id,
                username=current_user.username,
                clip_id=clip_id,
            )

            return {"status": "success", "message": "Clip deleted successfully"}
        else:
            logger.warning(
                f"Failed to delete clip {clip_id} - not found or access denied",
                extra={"user_id": current_user.user_id, "clip_id": clip_id},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clip not found or access denied",
            )

    except HTTPException:
        raise
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Error deleting clip {clip_id} for user {current_user.username}: {e}",
            extra={"user_id": current_user.user_id, "clip_id": clip_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete clip",
        )


@router.post("/bulk-delete")
async def bulk_delete_clips(
    request: BulkDeleteRequest,
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
    clip_service: ClipProcessingService = Depends(get_clip_processing_service),
) -> Dict[str, Any]:
    """Delete multiple clips (protected endpoint)"""
    try:
        logger.info(
            f"Bulk deleting {len(request.clip_ids)} clips for user {current_user.username}",
            extra={
                "user_id": current_user.user_id,
                "clip_count": len(request.clip_ids),
            },
        )

        deleted_count, failed_clips = await clip_service.bulk_delete_clips(
            request.clip_ids, current_user.user_id
        )

        result = {
            "status": "completed",
            "deleted_count": deleted_count,
            "total_requested": len(request.clip_ids),
            "failed_clips": [
                {"clip_id": cid, "reason": "Access denied or not found"} for cid in failed_clips
            ],
        }

        if failed_clips:
            result["message"] = f"Deleted {deleted_count} out of {len(request.clip_ids)} clips"
        else:
            result["message"] = f"Successfully deleted all {deleted_count} clips"

        logger.info(
            f"Bulk delete completed: {deleted_count}/{len(request.clip_ids)} clips deleted",
            extra={
                "user_id": current_user.user_id,
                "deleted_count": deleted_count,
                "failed_count": len(failed_clips),
            },
        )

        # Audit log bulk deletion
        log_clip_bulk_delete(
            user_id=current_user.user_id,
            username=current_user.username,
            clip_ids=request.clip_ids,
            deleted_count=deleted_count,
            failed_count=len(failed_clips),
        )

        return result

    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Bulk delete failed for user {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk delete operation failed",
        )


@router.delete("/edited/{edit_id}")
async def delete_edited_video(
    edit_id: str,
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Delete an individual edited video (protected endpoint)"""
    try:
        logger.info(
            f"Deleting edited video {edit_id} for user {current_user.username}",
            extra={"user_id": current_user.user_id, "edit_id": edit_id},
        )

        with get_db_session() as db:
            edit_repo = EditRepository(db)

            if edit_repo.delete_edit(edit_id, current_user.user_id):
                logger.info(
                    f"Successfully deleted edited video {edit_id} for user {current_user.username}",
                    extra={"user_id": current_user.user_id, "edit_id": edit_id},
                )
                return {
                    "status": "success",
                    "message": "Edited video deleted successfully",
                }
            else:
                logger.warning(
                    f"Failed to delete edited video {edit_id} - not found or access denied",
                    extra={"user_id": current_user.user_id, "edit_id": edit_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Edited video not found or access denied",
                )

    except HTTPException:
        raise
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Error deleting edited video {edit_id} for user {current_user.username}: {e}",
            extra={"user_id": current_user.user_id, "edit_id": edit_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete edited video",
        )
