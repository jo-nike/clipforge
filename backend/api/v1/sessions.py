"""
Sessions API Endpoints - FastAPI routes for Plex session management
Implements secure session operations with proper service layer separation
"""

from typing import Any, Dict, Optional, Tuple

from api.dependencies import (
    get_authenticated_user_with_plex_token,
    get_clip_processing_service,
    get_plex_service,
    handle_service_error,
    setup_request_context,
)
from core.exceptions import ClipForgeException, SessionNotFoundError
from core.logging import get_logger
from domain.schemas import (
    AllSessionsResponse,
    CurrentSessionResponse,
    MultiFrameRequest,
    MultiFrameResponse,
    SnapshotCleanupRequest,
    SnapshotRequest,
    SnapshotResponse,
)
from fastapi import APIRouter, Depends, HTTPException, status
from services.clip_service import ClipProcessingService
from services.plex_service import PlexService

logger = get_logger("sessions_api")
router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("/current", response_model=CurrentSessionResponse)
async def get_current_session(
    _: str = Depends(setup_request_context),
    user_and_token: Tuple = Depends(get_authenticated_user_with_plex_token),
    plex_service: PlexService = Depends(get_plex_service),
) -> CurrentSessionResponse:
    """Get current user's playback session (protected endpoint)"""
    current_user, plex_token = user_and_token

    try:
        logger.debug(
            f"Getting current session for user {current_user.username}",
            extra={"user_id": current_user.user_id},
        )

        session = await plex_service.get_current_session(plex_token, current_user.username)

        if session:
            logger.info(
                f"Found current session for user {current_user.username}",
                extra={"user_id": current_user.user_id},
            )
            return CurrentSessionResponse(has_session=True, session=session)
        else:
            logger.debug(
                f"No current session found for user {current_user.username}",
                extra={"user_id": current_user.user_id},
            )
            return CurrentSessionResponse(
                has_session=False, message="No active playback session found"
            )

    except SessionNotFoundError as e:
        logger.warning(
            f"Session retrieval failed for user {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        return CurrentSessionResponse(has_session=False, message=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to get current session for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve current session",
        )


@router.get("/all", response_model=AllSessionsResponse)
async def get_all_user_sessions(
    _: str = Depends(setup_request_context),
    user_and_token: Tuple = Depends(get_authenticated_user_with_plex_token),
    plex_service: PlexService = Depends(get_plex_service),
) -> AllSessionsResponse:
    """Get all user's playback sessions (protected endpoint)"""
    current_user, plex_token = user_and_token

    try:
        logger.debug(
            f"Getting all sessions for user {current_user.username}",
            extra={"user_id": current_user.user_id},
        )

        sessions = await plex_service.get_all_user_sessions(plex_token, current_user.username)

        if sessions:
            logger.info(
                f"Found {len(sessions)} sessions for user {current_user.username}",
                extra={"user_id": current_user.user_id, "session_count": len(sessions)},
            )
            return AllSessionsResponse(has_sessions=True, sessions=sessions)
        else:
            logger.debug(
                f"No sessions found for user {current_user.username}",
                extra={"user_id": current_user.user_id},
            )
            return AllSessionsResponse(
                has_sessions=False, message="No active playback sessions found"
            )

    except SessionNotFoundError as e:
        logger.warning(
            f"Sessions retrieval failed for user {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        return AllSessionsResponse(has_sessions=False, message=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to get all sessions for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user sessions",
        )


@router.get("/preview-frames")
async def generate_preview_frames(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    session_key: Optional[str] = None,
    _: str = Depends(setup_request_context),
    user_and_token: Tuple = Depends(get_authenticated_user_with_plex_token),
    clip_service: ClipProcessingService = Depends(get_clip_processing_service),
    plex_service: PlexService = Depends(get_plex_service),
) -> Dict[str, Any]:
    """Generate preview frames at start and end times for timeline preview (protected endpoint)"""
    current_user, plex_token = user_and_token

    try:
        logger.debug(
            f"Generating preview frames for user {current_user.username}",
            extra={
                "user_id": current_user.user_id,
                "start_time": start_time,
                "end_time": end_time,
            },
        )

        # Validate that at least one time is provided
        if not start_time and not end_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one time (start_time or end_time) must be provided",
            )

        # Get user's session (specific session if key provided, otherwise current session)
        if session_key:
            logger.debug(
                f"Using specific session {session_key} for preview frames for user {current_user.username}"
            )
            session = await plex_service.get_session_by_key(
                plex_token, current_user.username, session_key
            )
            if not session:
                logger.warning(
                    f"Specified session {session_key} not found for preview frames for user {current_user.username}",
                    extra={"user_id": current_user.user_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Specified session not found",
                )
        else:
            logger.debug(
                f"Using current session for preview frames for user {current_user.username}"
            )
            session = await plex_service.get_current_session(plex_token, current_user.username)
            if not session:
                logger.warning(
                    f"No active session found for preview frames for user {current_user.username}",
                    extra={"user_id": current_user.user_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active playback session found",
                )

        # Generate preview frames using the service
        preview_result = await clip_service.generate_preview_frames(
            session, start_time, end_time, plex_token, current_user.user_id
        )

        if preview_result["status"] == "failed":
            logger.error(
                f"Preview frame generation failed for user {current_user.username}: {preview_result.get('error_message')}",
                extra={"user_id": current_user.user_id},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=preview_result["error_message"],
            )

        logger.info(
            f"Successfully generated preview frames for user {current_user.username}",
            extra={"user_id": current_user.user_id},
        )

        return preview_result

    except HTTPException:
        raise
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to generate preview frames for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate preview frames: {str(e)}",
        )


@router.post("/snapshots/create", response_model=SnapshotResponse)
async def create_snapshot(
    request: SnapshotRequest,
    _: str = Depends(setup_request_context),
    user_and_token: Tuple = Depends(get_authenticated_user_with_plex_token),
    clip_service: ClipProcessingService = Depends(get_clip_processing_service),
    plex_service: PlexService = Depends(get_plex_service),
) -> SnapshotResponse:
    """Create a snapshot from current session (protected endpoint)"""
    current_user, plex_token = user_and_token

    try:
        logger.info(
            f"Creating snapshot for user {current_user.username}",
            extra={"user_id": current_user.user_id, "timestamp": request.timestamp},
        )

        # Get user's session (specific session if key provided, otherwise current session)
        if request.session_key:
            logger.debug(
                f"Using specific session {request.session_key} for snapshot for user {current_user.username}"
            )
            session = await plex_service.get_session_by_key(
                plex_token, current_user.username, request.session_key
            )
            if not session:
                logger.warning(
                    f"Specified session {request.session_key} not found for snapshot for user {current_user.username}",
                    extra={"user_id": current_user.user_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Specified session not found",
                )
        else:
            logger.debug(f"Using current session for snapshot for user {current_user.username}")
            session = await plex_service.get_current_session(plex_token, current_user.username)
            if not session:
                logger.warning(
                    f"No active session found for snapshot for user {current_user.username}",
                    extra={"user_id": current_user.user_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active playback session found",
                )

        # Create the snapshot using the service
        snapshot_response = await clip_service.create_snapshot(
            session, request, plex_token, current_user.user_id
        )

        logger.info(
            f"Successfully created snapshot {snapshot_response.snapshot_id} for user {current_user.username}",
            extra={
                "user_id": current_user.user_id,
                "snapshot_id": snapshot_response.snapshot_id,
            },
        )

        return snapshot_response

    except HTTPException:
        raise
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to create snapshot for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create snapshot: {str(e)}",
        )


@router.post("/snapshots/multi-frame", response_model=MultiFrameResponse)
async def create_multi_frame_snapshots(
    request: MultiFrameRequest,
    _: str = Depends(setup_request_context),
    user_and_token: Tuple = Depends(get_authenticated_user_with_plex_token),
    clip_service: ClipProcessingService = Depends(get_clip_processing_service),
    plex_service: PlexService = Depends(get_plex_service),
) -> MultiFrameResponse:
    """Create multiple frames around a center timestamp (protected endpoint)"""
    current_user, plex_token = user_and_token

    try:
        logger.info(
            f"Creating multi-frame snapshots for user {current_user.username}",
            extra={
                "user_id": current_user.user_id,
                "center_timestamp": request.center_timestamp,
                "frame_count_before": request.frame_count_before,
                "frame_count_after": request.frame_count_after,
            },
        )

        # Get user's session (specific session if key provided, otherwise current session)
        if request.session_key:
            logger.debug(
                f"Using specific session {request.session_key} for multi-frame snapshots for user {current_user.username}"
            )
            session = await plex_service.get_session_by_key(
                plex_token, current_user.username, request.session_key
            )
            if not session:
                logger.warning(
                    f"Specified session {request.session_key} not found for multi-frame snapshots for user {current_user.username}",
                    extra={"user_id": current_user.user_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Specified session not found",
                )
        else:
            logger.debug(
                f"Using current session for multi-frame snapshots for user {current_user.username}"
            )
            session = await plex_service.get_current_session(plex_token, current_user.username)
            if not session:
                logger.warning(
                    f"No active session found for multi-frame snapshots for user {current_user.username}",
                    extra={"user_id": current_user.user_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active playback session found",
                )

        # Create the multi-frame snapshots using the service
        multi_frame_response = await clip_service.create_multi_frame_snapshots(
            session, request, plex_token, current_user.user_id
        )

        frame_count = len(multi_frame_response.frames) if multi_frame_response.frames else 0
        logger.info(
            f"Successfully created {frame_count} multi-frame snapshots for user {current_user.username}",
            extra={"user_id": current_user.user_id, "frame_count": frame_count},
        )

        return multi_frame_response

    except HTTPException:
        raise
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to create multi-frame snapshots for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create multi-frame snapshots: {str(e)}",
        )


@router.post("/snapshots/cleanup")
async def cleanup_snapshot_frames(
    request: SnapshotCleanupRequest,
    _: str = Depends(setup_request_context),
    user_and_token: Tuple = Depends(get_authenticated_user_with_plex_token),
    clip_service: ClipProcessingService = Depends(get_clip_processing_service),
) -> Dict[str, Any]:
    """Clean up snapshot frames by frame IDs (protected endpoint)"""
    current_user, _ = user_and_token

    try:
        logger.info(
            f"Cleaning up {len(request.frame_ids)} snapshot frames for user {current_user.username}",
            extra={
                "user_id": current_user.user_id,
                "frame_count": len(request.frame_ids),
            },
        )

        # Clean up the snapshot frames using the service
        cleanup_result = await clip_service.cleanup_snapshot_frames(
            request.frame_ids, current_user.user_id
        )

        logger.info(
            f"Successfully cleaned up {cleanup_result.get('cleaned_count', 0)} snapshot frames for user {current_user.username}",
            extra={
                "user_id": current_user.user_id,
                "cleaned_count": cleanup_result.get("cleaned_count", 0),
            },
        )

        return {
            "status": "success",
            "message": f"Cleaned up {cleanup_result.get('cleaned_count', 0)} snapshot frames",
            "cleaned_count": cleanup_result.get("cleaned_count", 0),
            "errors": cleanup_result.get("errors", []),
        }

    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to cleanup snapshot frames for {current_user.username}: {e}",
            extra={"user_id": current_user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup snapshot frames: {str(e)}",
        )
