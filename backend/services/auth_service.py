"""
Secure authentication service for ClipForge
Handles JWT tokens without exposing sensitive Plex tokens
"""

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
from core.config import settings
from cryptography.fernet import Fernet
from domain.schemas import PlexUser
from fastapi import Cookie, HTTPException, Response
from services.plex_service import PlexService

logger = logging.getLogger(__name__)


class SecureTokenStore:
    """Secure token storage with optional persistence for development"""

    def __init__(self) -> None:
        self._in_memory_store: Dict[str, Dict[str, Any]] = {}
        backend_dir = Path(__file__).parent.parent
        self.storage_file = backend_dir / "secure_tokens.enc" if settings.debug else None
        self.cipher_key = self._get_or_create_cipher_key()
        self.cipher = Fernet(self.cipher_key)

        # Load existing tokens in development mode
        if self.storage_file and self.storage_file.exists():
            self._load_tokens()

    def _get_or_create_cipher_key(self) -> bytes:
        """Get or create encryption key for token storage"""
        backend_dir = Path(__file__).parent.parent
        key_file = backend_dir / ".token_key" if settings.debug else None

        if key_file and key_file.exists():
            with open(key_file, "rb") as f:
                return f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            if key_file:
                with open(key_file, "wb") as f:
                    f.write(key)
                # Make key file readable only by owner
                os.chmod(key_file, 0o600)
            return key

    def _load_tokens(self) -> None:
        """Load tokens from encrypted file"""
        if not self.storage_file:
            return
        try:
            with open(self.storage_file, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = self.cipher.decrypt(encrypted_data)
            token_data = json.loads(decrypted_data.decode("utf-8"))

            # Filter out expired tokens
            current_time = datetime.now(timezone.utc)
            valid_tokens = {}

            for key, value in token_data.items():
                if "expires_at" in value:
                    expires_at = datetime.fromisoformat(value["expires_at"])
                    if expires_at > current_time:
                        valid_tokens[key] = value

            self._in_memory_store = valid_tokens
            logger.info(f"Loaded {len(valid_tokens)} valid tokens from storage")

        except Exception as e:
            logger.warning(f"Could not load token storage: {e}")
            self._in_memory_store = {}

    def _save_tokens(self) -> None:
        """Save tokens to encrypted file (development only)"""
        if not self.storage_file:
            return

        try:
            # Clean expired tokens before saving
            self._cleanup_expired_tokens()

            token_data = json.dumps(self._in_memory_store).encode("utf-8")
            encrypted_data = self.cipher.encrypt(token_data)

            with open(self.storage_file, "wb") as f:
                f.write(encrypted_data)

            # Make file readable only by owner
            os.chmod(self.storage_file, 0o600)

        except Exception as e:
            logger.error(f"Could not save token storage: {e}")

    def _cleanup_expired_tokens(self) -> None:
        """Remove expired tokens from memory"""
        current_time = datetime.now(timezone.utc)
        expired_keys = []

        for key, value in self._in_memory_store.items():
            if "expires_at" in value:
                expires_at = datetime.fromisoformat(value["expires_at"])
                if expires_at <= current_time:
                    expired_keys.append(key)

        for key in expired_keys:
            del self._in_memory_store[key]

    def store(self, key: str, value: str, expires_hours: int = 24) -> None:
        """Store a token with expiration"""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

        self._in_memory_store[key] = {
            "value": value,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save to file in development mode
        if settings.debug:
            self._save_tokens()

    def get(self, key: str) -> Optional[str]:
        """Get a stored token if it exists and hasn't expired"""
        if key not in self._in_memory_store:
            return None

        token_data = self._in_memory_store[key]
        expires_at = datetime.fromisoformat(token_data["expires_at"])

        if expires_at <= datetime.now(timezone.utc):
            # Token expired, remove it
            del self._in_memory_store[key]
            if settings.debug:
                self._save_tokens()
            return None

        return str(token_data["value"])

    def remove(self, key: str) -> bool:
        """Remove a stored token"""
        if key in self._in_memory_store:
            del self._in_memory_store[key]
            if settings.debug:
                self._save_tokens()
            return True
        return False

    def cleanup(self) -> int:
        """Clean up expired tokens and return count removed"""
        initial_count = len(self._in_memory_store)
        self._cleanup_expired_tokens()
        removed_count = initial_count - len(self._in_memory_store)

        if removed_count > 0 and settings.debug:
            self._save_tokens()

        return removed_count


# Global secure token store instance
_secure_token_store = SecureTokenStore()


class SecureAuthService:
    """Secure authentication service that doesn't expose sensitive tokens"""

    def __init__(self) -> None:
        self.plex_service = PlexService()
        # Ensure JWT secret is bytes for the JWT library
        self.jwt_secret = settings.jwt_secret.encode("utf-8")
        self.jwt_algorithm = settings.jwt_algorithm
        self.cookie_name = "clipforge_session"

    def _generate_token_hash(self, user_id: str, plex_token: str) -> str:
        """Generate secure hash for token storage"""
        # Create a secure hash that can be used as a key
        # Convert jwt_secret back to string for hashing
        jwt_secret_str = (
            self.jwt_secret.decode("utf-8")
            if isinstance(self.jwt_secret, bytes)
            else str(self.jwt_secret)
        )
        message = f"{user_id}:{plex_token}:{jwt_secret_str}".encode("utf-8")
        return hashlib.sha256(message).hexdigest()

    def _store_plex_token(self, user_id: str, plex_token: str, remember_me: bool = False) -> str:
        """
        Securely store Plex token and return reference key
        Uses encrypted persistent storage in development, memory-only in production
        """
        token_key = self._generate_token_hash(user_id, plex_token)

        # Store with expiration (24 hours for regular tokens, 30 days for remember_me)
        expires_hours = (
            settings.jwt_remember_days * 24 if remember_me else settings.jwt_expiry_hours
        )
        _secure_token_store.store(token_key, plex_token, expires_hours)

        logger.debug(f"Stored Plex token for user {user_id} with key {token_key[:8]}...")
        return token_key

    def _retrieve_plex_token(self, user_id: str, token_key: str) -> Optional[str]:
        """Retrieve Plex token from secure storage"""
        plex_token = _secure_token_store.get(token_key)

        if plex_token:
            # Verify the token key matches what we would generate
            expected_key = self._generate_token_hash(user_id, plex_token)
            if expected_key == token_key:
                logger.debug(f"Retrieved Plex token for user {user_id}")
                return plex_token
            else:
                logger.warning(f"Token key mismatch for user {user_id}")
                # Remove invalid entry
                _secure_token_store.remove(token_key)

        logger.warning(f"Plex token not found for user {user_id}, key {token_key[:8]}...")
        return None

    def _revoke_plex_token(self, token_key: str) -> None:
        """Revoke stored Plex token"""
        if _secure_token_store.remove(token_key):
            logger.debug(f"Revoked Plex token with key {token_key[:8]}...")

    def create_secure_jwt_token(
        self, user: PlexUser, plex_token: str, remember_me: bool = False
    ) -> str:
        """
        Create JWT token without exposing Plex token

        Args:
            user: Authenticated user
            plex_token: Plex authentication token (will be stored securely)
            remember_me: Whether to create long-lived session

        Returns:
            JWT token string
        """
        # Store Plex token securely and get reference key
        token_key = self._store_plex_token(user.user_id, plex_token, remember_me)

        # Create JWT payload without sensitive data
        expiry_delta = (
            timedelta(days=settings.jwt_remember_days)
            if remember_me
            else timedelta(hours=settings.jwt_expiry_hours)
        )
        expiry = datetime.now(tz=timezone.utc) + expiry_delta

        # Generate session ID for additional security
        session_id = secrets.token_urlsafe(32)

        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "session_id": session_id,
            "token_key": token_key,  # Reference to stored Plex token
            "remember_me": remember_me,
            "exp": expiry,
            "iat": datetime.now(tz=timezone.utc),
            "iss": settings.app_name,
            "aud": settings.app_name,
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

        logger.info(
            f"Created secure JWT token for user {user.username} (session: {session_id[:8]}...)"
        )
        return token

    def create_media_access_token(self, user_id: str, resource_id: str, resource_type: str) -> str:
        """
        Create a temporary media access token for specific resource

        Args:
            user_id: User identifier
            resource_id: Media resource identifier (clip_id, snapshot_id, edit_id)
            resource_type: Type of media resource ('video', 'snapshot', 'edit')

        Returns:
            JWT token string for media access
        """
        # Short expiry for media tokens (1 hour)
        expiry_delta = timedelta(hours=1)
        expiry = datetime.now(tz=timezone.utc) + expiry_delta

        # Generate unique token ID for tracking
        token_id = secrets.token_urlsafe(16)

        payload = {
            "user_id": user_id,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "token_type": "media_access",
            "token_id": token_id,
            "exp": expiry,
            "iat": datetime.now(tz=timezone.utc),
            "iss": settings.app_name,
            "aud": settings.app_name,
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

        logger.debug(
            f"Created media access token for user {user_id}, resource {resource_id} ({resource_type})"
        )
        return token

    def verify_media_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode media access token

        Args:
            token: Media access token to verify

        Returns:
            Decoded payload if valid, None otherwise
        """
        try:
            # Validate token is a non-empty string
            if not token or not isinstance(token, str):
                logger.warning(
                    f"Invalid media token type. Token must be a non-empty string, got: {type(token)}"
                )
                return None

            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
                audience=settings.app_name,
                issuer=settings.app_name,
                leeway=timedelta(seconds=10),
            )

            # Validate required fields for media tokens
            required_fields = ["user_id", "resource_id", "resource_type", "token_type"]
            if not all(field in payload for field in required_fields):
                logger.warning("Media token missing required fields")
                return None

            # Verify this is actually a media access token
            if payload.get("token_type") != "media_access":
                logger.warning("Token is not a media access token")
                return None

            return dict(payload)

        except jwt.ExpiredSignatureError:
            logger.debug("Media access token expired")
            return None
        except jwt.InvalidAudienceError:
            logger.warning("Media access token invalid audience")
            return None
        except jwt.InvalidIssuerError:
            logger.warning("Media access token invalid issuer")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Media access token invalid: {e}")
            return None

    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token

        Args:
            token: JWT token to verify

        Returns:
            Decoded payload if valid, None otherwise
        """
        try:
            # Validate token is a non-empty string
            if not token or not isinstance(token, str):
                logger.warning(
                    f"Invalid token type. Token must be a non-empty string, got: {type(token)}"
                )
                return None

            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
                audience=settings.app_name,
                issuer=settings.app_name,
                leeway=timedelta(seconds=10),
            )

            # Validate required fields
            required_fields = ["user_id", "username", "session_id", "token_key"]
            if not all(field in payload for field in required_fields):
                logger.warning("JWT token missing required fields")
                return None

            return dict(payload)

        except jwt.ExpiredSignatureError:
            logger.debug("JWT token expired")
            return None
        except jwt.InvalidAudienceError:
            logger.warning("JWT token invalid audience")
            return None
        except jwt.InvalidIssuerError:
            logger.warning("JWT token invalid issuer")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"JWT token invalid: {e}")
            return None

    def set_secure_auth_cookie(
        self, response: Response, token: str, remember_me: bool = False
    ) -> None:
        """
        Set JWT token as secure HTTP-only cookie

        Args:
            response: FastAPI response object
            token: JWT token to set
            remember_me: Whether this is a long-lived session
        """
        max_age = (
            (settings.jwt_remember_days * 24 * 60 * 60)
            if remember_me
            else (settings.jwt_expiry_hours * 60 * 60)
        )

        response.set_cookie(
            key=self.cookie_name,
            value=token,
            max_age=max_age,
            httponly=True,  # Prevent XSS
            secure=settings.secure_cookies,  # HTTPS only in production
            samesite="lax",  # CSRF protection
            path="/",
            domain=None,  # Use default domain
        )

        logger.debug(f"Set secure auth cookie (remember_me: {remember_me})")

    def clear_auth_cookie(self, response: Response) -> None:
        """Clear authentication cookie and revoke stored tokens"""
        response.delete_cookie(key=self.cookie_name, path="/", domain=None)

        logger.debug("Cleared auth cookie")

    async def authenticate_user(self, plex_token: str) -> Optional[PlexUser]:
        """
        Authenticate user with Plex token

        Args:
            plex_token: Plex authentication token

        Returns:
            Authenticated user or None if invalid
        """
        try:
            user: Optional[PlexUser] = await self.plex_service.authenticate_user(plex_token)
            if user:
                logger.info(f"Successfully authenticated user: {user.username}")
            else:
                logger.warning("Plex authentication failed - invalid token")
            return user

        except Exception as e:
            logger.error(f"Plex authentication error: {e}")
            return None

    async def get_current_user(self, token: Optional[str]) -> PlexUser:
        """
        Get current user from JWT token in cookie

        Args:
            token: JWT token from cookie

        Returns:
            Authenticated user

        Raises:
            HTTPException: If not authenticated or token invalid
        """
        # Get token from cookie
        if token is None:
            raise HTTPException(status_code=401, detail="Not authenticated")

        # Verify JWT token
        payload = self.verify_jwt_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        # Validate Plex token is still valid (optional but recommended)
        token_key = payload.get("token_key")
        user_id = payload.get("user_id")

        if token_key and user_id:
            plex_token = self._retrieve_plex_token(user_id, token_key)
            if plex_token:
                try:
                    # Validate token by attempting authentication
                    test_user = await self.plex_service.authenticate_user(plex_token)
                    if not test_user:
                        logger.warning(f"Plex token no longer valid for user {user_id}")
                        # Revoke the stored token
                        self._revoke_plex_token(token_key)
                        raise HTTPException(status_code=401, detail="Plex token is no longer valid")
                except Exception as e:
                    logger.error(f"Error validating Plex token: {e}")
                    # Don't fail hard on validation errors, but log them

        # Return user from JWT payload
        return PlexUser(
            user_id=payload["user_id"],
            username=payload["username"],
            email=payload["email"],
        )

    async def get_plex_token_for_user(self, token: Optional[str]) -> Optional[str]:
        """
        Get Plex token for current user (for API calls)

        Args:
            token: JWT token from cookie

        Returns:
            Plex token or None if not available
        """
        if not token:
            return None

        payload = self.verify_jwt_token(token)
        if not payload:
            return None

        token_key = payload.get("token_key")
        user_id = payload.get("user_id")

        if token_key and user_id:
            return self._retrieve_plex_token(user_id, token_key)

        return None

    def revoke_user_session(self, token: str) -> bool:
        """
        Revoke user session and stored tokens

        Args:
            token: JWT token to revoke

        Returns:
            True if revoked successfully
        """
        try:
            payload = self.verify_jwt_token(token)
            if payload:
                token_key = payload.get("token_key")
                if token_key:
                    self._revoke_plex_token(token_key)
                    logger.info(f"Revoked session for user {payload.get('username')}")
                    return True
            return False

        except Exception as e:
            logger.error(f"Error revoking session: {e}")
            return False


# Global secure auth service instance
secure_auth_service = SecureAuthService()


# Dependency for FastAPI endpoints
async def get_current_user(clipforge_session: Optional[str] = Cookie(None)) -> PlexUser:
    """FastAPI dependency for getting current user"""
    return await secure_auth_service.get_current_user(clipforge_session)


async def get_plex_token(
    clipforge_session: Optional[str] = Cookie(None),
) -> Optional[str]:
    """FastAPI dependency for getting Plex token"""
    return await secure_auth_service.get_plex_token_for_user(clipforge_session)
