"""
Storage API Endpoints - FastAPI routes for storage management
Implements secure file serving and storage operations
"""

import os
from typing import Any, Dict, Optional

from api.dependencies import (
    get_authenticated_user,
    get_storage_service,
    handle_service_error,
    setup_request_context,
)
from core.exceptions import ClipForgeException, FileAccessError, FileNotFoundError
from core.logging import get_logger
from domain.schemas import PlexUser
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from infrastructure.database import get_db_session
from infrastructure.repositories import ClipRepository, EditRepository
from services.secure_storage_service import SecureStorageService

logger = get_logger("storage_api")
router = APIRouter(prefix="/storage", tags=["Storage"])


def authenticate_media_request(
    resource_id: str, resource_type: str, token: Optional[str] = None
) -> PlexUser:
    """
    Authenticate media request using either cookie or token authentication
    """
    from services.auth_service import secure_auth_service

    # If token is provided, use token authentication
    if token:
        payload = secure_auth_service.verify_media_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired media token",
            )

        # Verify token is for this specific resource
        if payload.get("resource_type") != resource_type:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token not valid for {resource_type} resources",
            )

        if payload.get("resource_id") != resource_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token not valid for this specific resource",
            )

        return PlexUser(
            user_id=payload["user_id"],
            username="",
            email="",
        )

    # If no token, this will be handled by the dependency injection system
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


@router.get("/stats")
async def get_storage_stats(
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Get storage statistics for current user (protected endpoint)"""
    try:
        logger.debug(
            f"Getting storage stats for user {current_user.username}",
            extra={"user_id": current_user.user_id},
        )

        # Use SecureStorageService with repository pattern
        from services.secure_storage_service import SecureStorageService

        storage_service = SecureStorageService()
        stats = storage_service.get_storage_stats(current_user.user_id)

        logger.debug(
            f"Retrieved storage stats for user {current_user.username}",
            extra={"user_id": current_user.user_id},
        )

        return stats

    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to get storage stats for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve storage statistics",
        )


@router.post("/cleanup")
async def cleanup_storage(
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """Manually trigger storage cleanup for current user (protected endpoint)"""
    try:
        logger.info(
            f"Starting storage cleanup for user {current_user.username}",
            extra={"user_id": current_user.user_id},
        )

        # Use SecureStorageService with repository pattern
        from services.secure_storage_service import SecureStorageService

        storage_service = SecureStorageService()
        result = await storage_service.cleanup_old_files(current_user.user_id)

        logger.info(
            f"Storage cleanup completed for user {current_user.username}",
            extra={"user_id": current_user.user_id},
        )

        return {"status": "success", "message": "Cleanup completed", "result": result}

    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Storage cleanup failed for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cleanup failed: {str(e)}",
        )


# Secure file serving endpoints
@router.get("/video/{clip_id}")
async def secure_video_stream(
    clip_id: str,
    request: Request,
    token: Optional[str] = Query(None, description="Media access token"),
    download: bool = Query(False, description="Force download instead of streaming"),
    _: str = Depends(setup_request_context),
    storage_service: SecureStorageService = Depends(get_storage_service),
) -> FileResponse:
    """Securely stream video file with user ownership validation"""
    try:
        # Handle authentication - either through cookie or token
        authenticated_user = None

        if token:
            # Use token authentication
            authenticated_user = authenticate_media_request(clip_id, "video", token)
        else:
            # Try cookie authentication
            try:
                from services.auth_service import secure_auth_service

                cookie_value = request.cookies.get("clipforge_session")
                authenticated_user = await secure_auth_service.get_current_user(cookie_value)
            except HTTPException:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required. Please log in or provide a valid media token.",
                )

        logger.debug(
            f"Streaming video {clip_id} for user {authenticated_user.user_id}",
            extra={"user_id": authenticated_user.user_id, "clip_id": clip_id},
        )

        with get_db_session() as db:
            clip_repo = ClipRepository(db)
            clip = clip_repo.get_by_id(clip_id, authenticated_user.user_id)

            if not clip:
                logger.warning(
                    f"Video {clip_id} not found or access denied for user {authenticated_user.user_id}",
                    extra={"user_id": authenticated_user.user_id, "clip_id": clip_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Clip not found or access denied",
                )

            # Use secure storage service to stream file
            response = storage_service.stream_video_file(
                clip_id=str(clip.id),
                user_id=authenticated_user.user_id,
                file_path=str(clip.file_path),
                force_download=download,
            )

            logger.debug(
                f"Successfully streaming video {clip_id} for user {authenticated_user.user_id}",
                extra={"user_id": authenticated_user.user_id, "clip_id": clip_id},
            )

            return response

    except HTTPException:
        raise
    except (FileNotFoundError, FileAccessError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        user_id = authenticated_user.user_id if authenticated_user else "unknown"
        username = authenticated_user.username if authenticated_user else "unknown"
        logger.error(
            f"Failed to stream video {clip_id} for user {username}: {e}",
            extra={"user_id": user_id, "clip_id": clip_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stream video",
        )


@router.get("/snapshot/{snapshot_id}")
async def secure_snapshot_stream(
    snapshot_id: str,
    request: Request,
    token: Optional[str] = Query(None, description="Media access token"),
    _: str = Depends(setup_request_context),
    storage_service: SecureStorageService = Depends(get_storage_service),
) -> FileResponse:
    """Securely stream snapshot file with user ownership validation"""
    try:
        # Handle authentication - either through cookie or token
        authenticated_user = None

        if token:
            # Use token authentication
            authenticated_user = authenticate_media_request(snapshot_id, "snapshot", token)
        else:
            # Try cookie authentication
            try:
                from services.auth_service import secure_auth_service

                cookie_value = request.cookies.get("clipforge_session")
                authenticated_user = await secure_auth_service.get_current_user(cookie_value)
            except HTTPException:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required. Please log in or provide a valid media token.",
                )

        logger.debug(
            f"Streaming snapshot {snapshot_id} for user {authenticated_user.user_id}",
            extra={"user_id": authenticated_user.user_id, "snapshot_id": snapshot_id},
        )

        response = storage_service.stream_temporary_file(snapshot_id, authenticated_user.user_id)

        logger.debug(
            f"Successfully streaming snapshot {snapshot_id} for user {authenticated_user.user_id}",
            extra={"user_id": authenticated_user.user_id, "snapshot_id": snapshot_id},
        )

        return response

    except (FileNotFoundError, FileAccessError) as e:
        user_id = authenticated_user.user_id if authenticated_user else "unknown"
        logger.warning(
            f"Snapshot {snapshot_id} not found or access denied for user {user_id}: {e}",
            extra={"user_id": user_id, "snapshot_id": snapshot_id},
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        user_id = authenticated_user.user_id if authenticated_user else "unknown"
        logger.error(
            f"Failed to stream snapshot {snapshot_id} for user {user_id}: {e}",
            extra={"user_id": user_id, "snapshot_id": snapshot_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stream snapshot",
        )


@router.get("/edit/{edit_id}")
async def secure_edit_stream(
    edit_id: str,
    request: Request,
    token: Optional[str] = Query(None, description="Media access token"),
    download: bool = Query(False, description="Force download instead of streaming"),
    _: str = Depends(setup_request_context),
    storage_service: SecureStorageService = Depends(get_storage_service),
) -> FileResponse:
    """Securely stream edited video file with user ownership validation"""
    try:
        # Handle authentication - either through cookie or token
        authenticated_user = None

        if token:
            # Use token authentication
            authenticated_user = authenticate_media_request(edit_id, "edit", token)
        else:
            # Try cookie authentication
            try:
                from services.auth_service import secure_auth_service

                cookie_value = request.cookies.get("clipforge_session")
                authenticated_user = await secure_auth_service.get_current_user(cookie_value)
            except HTTPException:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required. Please log in or provide a valid media token.",
                )

        logger.debug(
            f"Streaming edited video {edit_id} for user {authenticated_user.user_id}",
            extra={"user_id": authenticated_user.user_id, "edit_id": edit_id},
        )

        with get_db_session() as db:
            edit_repo = EditRepository(db)
            edit = edit_repo.get_by_id(edit_id, authenticated_user.user_id)

            if not edit:
                logger.warning(
                    f"Edited video {edit_id} not found or access denied for user {authenticated_user.user_id}",
                    extra={"user_id": authenticated_user.user_id, "edit_id": edit_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Edited video not found or access denied",
                )

            if not edit.file_path or not os.path.exists(edit.file_path):
                logger.warning(
                    f"Edited video file not found: {edit.file_path}",
                    extra={"user_id": authenticated_user.user_id, "edit_id": edit_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Edited video file not found",
                )

            # Use secure storage service to stream file
            response = storage_service.stream_video_file(
                clip_id=str(edit.id),
                user_id=authenticated_user.user_id,
                file_path=str(edit.file_path),
                force_download=download,
            )

            logger.debug(
                f"Successfully streaming edited video {edit_id} for user {authenticated_user.user_id}",
                extra={"user_id": authenticated_user.user_id, "edit_id": edit_id},
            )

            return response

    except HTTPException:
        raise
    except (FileNotFoundError, FileAccessError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        user_id = authenticated_user.user_id if authenticated_user else "unknown"
        logger.error(
            f"Failed to stream edit {edit_id} for user {user_id}: {e}",
            extra={"user_id": user_id, "edit_id": edit_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stream edited video",
        )


@router.get("/thumbnail/{clip_id}")
async def secure_thumbnail_stream(
    clip_id: str,
    request: Request,
    token: Optional[str] = Query(None, description="Media access token"),
    _: str = Depends(setup_request_context),
    storage_service: SecureStorageService = Depends(get_storage_service),
) -> FileResponse:
    """Securely stream thumbnail file with user ownership validation"""
    try:
        # Handle authentication - either through cookie or token
        authenticated_user = None

        if token:
            # Use token authentication
            authenticated_user = authenticate_media_request(clip_id, "thumbnail", token)
        else:
            # Try cookie authentication
            try:
                from services.auth_service import secure_auth_service

                cookie_value = request.cookies.get("clipforge_session")
                authenticated_user = await secure_auth_service.get_current_user(cookie_value)
            except HTTPException:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required. Please log in or provide a valid media token.",
                )

        logger.debug(
            f"Streaming thumbnail {clip_id} for user {authenticated_user.user_id}",
            extra={"user_id": authenticated_user.user_id, "clip_id": clip_id},
        )

        with get_db_session() as db:
            clip_repo = ClipRepository(db)
            clip = clip_repo.get_by_id(clip_id, authenticated_user.user_id)

            if not clip:
                logger.warning(
                    f"Clip {clip_id} not found or access denied for user {authenticated_user.user_id}",
                    extra={"user_id": authenticated_user.user_id, "clip_id": clip_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Clip not found or access denied",
                )

            # Construct thumbnail path
            from core.config import settings

            thumbnail_filename = f"thumb_{clip_id}.jpg"
            thumbnail_path = settings.absolute_clips_path / "thumbnails" / thumbnail_filename

            if not thumbnail_path.exists():
                logger.warning(
                    f"Thumbnail {thumbnail_filename} not found for clip {clip_id}",
                    extra={"user_id": authenticated_user.user_id, "clip_id": clip_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Thumbnail not found",
                )

            # Use secure storage service to stream file
            response = storage_service.stream_image_file(
                image_id=f"thumb_{clip_id}",
                user_id=authenticated_user.user_id,
                file_path=str(thumbnail_path),
            )

            logger.debug(
                f"Successfully streaming thumbnail {clip_id} for user {authenticated_user.user_id}",
                extra={"user_id": authenticated_user.user_id, "clip_id": clip_id},
            )

            return response

    except HTTPException:
        raise
    except (FileNotFoundError, FileAccessError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        user_id = authenticated_user.user_id if authenticated_user else "unknown"
        logger.error(
            f"Failed to stream thumbnail {clip_id} for user {user_id}: {e}",
            extra={"user_id": user_id, "clip_id": clip_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stream thumbnail",
        )
