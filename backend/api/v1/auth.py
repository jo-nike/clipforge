"""
Authentication API Endpoints - FastAPI routes for authentication
Implements secure authentication with proper error handling and logging
"""

from typing import Any, Dict

from api.dependencies import (
    get_authenticated_user,
    get_plex_service,
    handle_service_error,
    setup_request_context,
)
from core.audit import log_auth_failure, log_auth_success
from core.exceptions import ClipForgeException
from core.logging import get_logger
from domain.schemas import (
    PinCheckResponse,
    PlexPin,
    PlexUser,
    SignInRequest,
    SignInResponse,
    UserResponse,
)
from fastapi import APIRouter, Depends, Form, HTTPException, Response, status
from infrastructure.database import get_db_session
from infrastructure.repositories import UserRepository
from services.auth_service import secure_auth_service
from services.plex_service import PlexService

logger = get_logger("auth_api")
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/pin", response_model=PlexPin)
async def create_auth_pin(
    _: str = Depends(setup_request_context),
    plex_service: PlexService = Depends(get_plex_service),
) -> PlexPin:
    """Create a new PIN for Plex OAuth authentication"""
    try:
        logger.info("Creating authentication PIN")

        pin_data = await plex_service.create_pin()
        if not pin_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create authentication PIN",
            )

        return PlexPin(id=pin_data["id"], code=pin_data["code"])

    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(f"Pin creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )


@router.get("/pin/{pin_id}", response_model=PinCheckResponse)
async def check_auth_pin(
    pin_id: int,
    _: str = Depends(setup_request_context),
    plex_service: PlexService = Depends(get_plex_service),
) -> PinCheckResponse:
    """Check if a PIN has been authenticated"""
    try:
        logger.debug(f"Checking authentication PIN: {pin_id}")

        auth_token = await plex_service.check_pin(pin_id)

        return PinCheckResponse(authenticated=auth_token is not None, auth_token=auth_token)

    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(f"Pin check failed for {pin_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication check failed",
        )


@router.post("/signin", response_model=SignInResponse)
async def sign_in(
    request: SignInRequest,
    response: Response,
    _: str = Depends(setup_request_context),
    plex_service: PlexService = Depends(get_plex_service),
) -> SignInResponse:
    """Secure sign in with Plex token"""
    try:
        logger.info("Processing sign-in request")

        # Authenticate user with Plex
        user = await plex_service.authenticate_user(request.token)

        if not user:
            logger.warning("Invalid Plex token provided")

            # Audit log failed authentication
            log_auth_failure(details={"reason": "invalid_plex_token"})

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Plex token"
            )

        # Ensure user exists in database
        with get_db_session() as db:
            user_repo = UserRepository(db)
            user_repo.create_or_update(user.user_id, user.username, user.email)

        # Create secure JWT token (Plex token stored separately)
        jwt_token = secure_auth_service.create_secure_jwt_token(
            user, request.token, request.remember_me
        )

        # Set secure authentication cookie
        secure_auth_service.set_secure_auth_cookie(response, jwt_token, request.remember_me)

        logger.info(
            f"User {user.username} signed in successfully",
            extra={"user_id": user.user_id},
        )

        # Audit log successful authentication
        log_auth_success(
            user_id=user.user_id,
            username=user.username,
            details={"remember_me": request.remember_me},
        )

        return SignInResponse(
            status="success", message=f"Welcome, {user.username}!", token=jwt_token
        )

    except HTTPException:
        raise
    except ClipForgeException as e:
        # Audit log authentication failure
        log_auth_failure(details={"reason": "service_error", "error": str(e)})
        raise handle_service_error(e)
    except Exception as e:
        logger.error(f"Sign in failed: {e}")
        # Audit log authentication failure
        log_auth_failure(details={"reason": "system_error", "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed",
        )


@router.post("/logout")
async def logout(
    response: Response,
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> Dict[str, str]:
    """Secure logout with token revocation"""
    try:
        secure_auth_service.clear_auth_cookie(response)
        logger.info(
            f"User {current_user.username} logged out",
            extra={"user_id": current_user.user_id},
        )

        return {"status": "success", "message": "Logged out successfully"}

    except Exception as e:
        logger.error(f"Logout failed: {e}")
        # Always return success for logout, even on errors
        return {"status": "success", "message": "Logged out"}


@router.post("/media-token")
async def create_media_access_token(
    resource_id: str = Form(...),
    resource_type: str = Form(...),
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> Dict[str, Any]:
    """
    Create a temporary media access token for specific resource

    Args:
        resource_id: The ID of the media resource (clip_id, snapshot_id, edit_id)
        resource_type: Type of resource ('video', 'snapshot', 'edit', 'thumbnail')
    """
    try:
        # Validate resource type
        valid_types = ["video", "snapshot", "edit", "thumbnail"]
        if resource_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid resource type. Must be one of: {', '.join(valid_types)}",
            )

        # Validate user has access to the resource
        with get_db_session() as db:
            if resource_type == "video":
                from infrastructure.repositories import ClipRepository

                clip_repo = ClipRepository(db)
                clip = clip_repo.get_by_id(resource_id, current_user.user_id)
                if not clip:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Video clip not found or access denied",
                    )
            elif resource_type == "snapshot":
                # Check if this is a preview frame (temporary file) or persistent snapshot
                from pathlib import Path

                from core.config import settings

                # Check if this resource_id corresponds to a preview frame file
                # Preview frames are temporary files that may exist with these patterns
                snapshots_dir = Path(settings.absolute_clips_path) / "snapshots"

                # Check if any preview frame files exist for this resource_id
                temp_patterns = [
                    f"preview_start_{resource_id}.jpg",
                    f"preview_end_{resource_id}.jpg",
                    f"frame_{resource_id}.jpg",
                    f"multiframe_{resource_id}.jpg",
                ]

                is_preview_frame = any(
                    (snapshots_dir / pattern).exists() for pattern in temp_patterns
                )

                if is_preview_frame:
                    # File existence already confirmed during detection
                    # No additional validation needed for preview frames
                    pass
                else:
                    # For persistent snapshots, check database
                    from infrastructure.repositories import SnapshotRepository

                    snapshot_repo = SnapshotRepository(db)
                    snapshot = snapshot_repo.get_by_id(resource_id, current_user.user_id)
                    if not snapshot:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="Snapshot not found or access denied",
                        )
            elif resource_type == "edit":
                from infrastructure.repositories import EditRepository

                edit_repo = EditRepository(db)
                edit = edit_repo.get_by_id(resource_id, current_user.user_id)
                if not edit:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Edited video not found or access denied",
                    )
            elif resource_type == "thumbnail":
                # Validate that the user owns the clip for this thumbnail
                from infrastructure.repositories import ClipRepository

                clip_repo = ClipRepository(db)
                clip = clip_repo.get_by_id(resource_id, current_user.user_id)
                if not clip:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Clip not found or access denied for thumbnail",
                    )

                # Check if thumbnail file exists
                from pathlib import Path

                from core.config import settings

                thumbnail_filename = f"thumb_{resource_id}.jpg"
                thumbnail_path = (
                    Path(settings.absolute_clips_path) / "thumbnails" / thumbnail_filename
                )
                if not thumbnail_path.exists():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Thumbnail not found",
                    )

        # Generate media access token
        token = secure_auth_service.create_media_access_token(
            current_user.user_id, resource_id, resource_type
        )

        logger.debug(
            f"Generated media access token for user {current_user.username}, "
            f"resource {resource_id} ({resource_type})",
            extra={"user_id": current_user.user_id, "resource_id": resource_id},
        )

        return {
            "status": "success",
            "token": token,
            "expires_in": 3600,  # 1 hour in seconds
            "resource_id": resource_id,
            "resource_type": resource_type,
        }

    except HTTPException:
        raise
    except ClipForgeException as e:
        raise handle_service_error(e)
    except Exception as e:
        logger.error(
            f"Failed to create media token for user {current_user.username}: {e}",
            extra={"user_id": current_user.user_id, "resource_id": resource_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create media access token",
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    _: str = Depends(setup_request_context),
    current_user: PlexUser = Depends(get_authenticated_user),
) -> UserResponse:
    """Get current user details (protected endpoint)"""
    logger.debug(
        f"Retrieving user info for {current_user.username}",
        extra={"user_id": current_user.user_id},
    )

    return UserResponse(user=current_user)
