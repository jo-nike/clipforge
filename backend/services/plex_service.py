"""
Plex Integration Service - Service layer for Plex operations
Implements IPlexService interface with proper error handling and logging
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from core.config import settings
from core.exceptions import (
    ExternalServiceError,
    PlexAuthenticationError,
    PlexConnectionError,
    SessionNotFoundError,
)
from core.logging import get_logger, performance_logger
from core.resilience import with_plex_retry
from defusedxml import ElementTree as ET
from domain.interfaces import IPlexService
from domain.schemas import (
    MediaInfo,
    OriginalFileInfo,
    PlayerInfo,
    PlexGuid,
    PlexServer,
    PlexServerConnection,
    PlexSessionInfo,
    PlexStreamMedia,
    PlexStreamPart,
    PlexUser,
    SessionInfo,
)


class PlexService(IPlexService):
    """Service for Plex server integration and session management"""

    def __init__(self) -> None:
        self.base_url = "https://plex.tv"
        self.timeout = 30.0
        self.client_id = "clipforge-v1"
        self.logger = get_logger("plex_service")

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """Generate Plex API headers"""
        headers = {
            "Accept": "application/json",
            "X-Plex-Product": "clipforge-v1",
            "X-Plex-Version": "1.0.0",
            "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Platform": "Web",
            "X-Plex-Platform-Version": "1.0",
            "X-Plex-Model": "Plex OAuth",
            "X-Plex-Device": "Browser",
            "X-Plex-Device-Name": "clipforge-v1",
            "X-Plex-Language": "en",
            "Content-Type": "application/json",
        }

        if token:
            headers["X-Plex-Token"] = token

        return headers

    @with_plex_retry()
    async def create_pin(self) -> Optional[Dict[str, Any]]:
        """Create a new PIN for Plex OAuth authentication"""
        start_time = datetime.now()

        try:
            self.logger.info("Creating Plex authentication PIN")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v2/pins?strong=true",
                    headers=self._get_headers(),
                )

                if response.status_code == 201:
                    data = response.json()
                    pin_data = {"id": data["id"], "code": data["code"]}

                    # Log performance
                    duration = (datetime.now() - start_time).total_seconds() * 1000
                    performance_logger.log_request_duration(
                        "plex_create_pin", "POST", duration, response.status_code
                    )

                    self.logger.info(f"Successfully created Plex PIN: {pin_data['id']}")
                    return pin_data
                else:
                    self.logger.warning(f"Failed to create Plex PIN: {response.status_code}")

        except httpx.TimeoutException:
            self.logger.error("Timeout creating Plex PIN")
            raise PlexConnectionError("Plex service timeout during PIN creation")
        except httpx.RequestError as e:
            self.logger.error(f"Network error creating Plex PIN: {e}")
            raise PlexConnectionError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error creating Plex PIN: {e}")
            raise ExternalServiceError(f"PIN creation failed: {e}")

        return None

    @with_plex_retry()
    async def check_pin(self, pin_id: int) -> Optional[str]:
        """Check if a PIN has been authenticated and return auth token"""
        start_time = datetime.now()

        try:
            self.logger.debug(f"Checking Plex PIN: {pin_id}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v2/pins/{pin_id}", headers=self._get_headers()
                )

                if response.status_code == 200:
                    data = response.json()
                    auth_token = data.get("authToken")

                    # Log performance
                    duration = (datetime.now() - start_time).total_seconds() * 1000
                    performance_logger.log_request_duration(
                        "plex_check_pin", "GET", duration, response.status_code
                    )

                    if auth_token:
                        self.logger.info(f"PIN {pin_id} successfully authenticated")
                        return str(auth_token) if auth_token else None
                    else:
                        self.logger.debug(f"PIN {pin_id} not yet authenticated")
                        return None
                else:
                    self.logger.warning(f"Failed to check PIN {pin_id}: {response.status_code}")

        except httpx.TimeoutException:
            self.logger.error(f"Timeout checking PIN {pin_id}")
            raise PlexConnectionError("Plex service timeout during PIN check")
        except httpx.RequestError as e:
            self.logger.error(f"Network error checking PIN {pin_id}: {e}")
            raise PlexConnectionError(f"Network error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error checking PIN {pin_id}: {e}")
            raise ExternalServiceError(f"PIN check failed: {e}")

        return None

    @with_plex_retry()
    async def authenticate_user(self, auth_token: str) -> Optional[PlexUser]:
        """Authenticate user with Plex token and return user info"""
        start_time = datetime.now()

        try:
            self.logger.info("Authenticating user with Plex token")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = self._get_headers(auth_token)

                response = await client.get(f"{self.base_url}/users/account", headers=headers)

                if response.status_code == 200:
                    # Plex returns XML for user account details
                    xml_content = response.text
                    root = ET.fromstring(xml_content)

                    if root.tag == "user":
                        user = PlexUser(
                            user_id=root.get("id", ""),
                            username=root.get("username", ""),
                            email=root.get("email", ""),
                            thumb=root.get("thumb", ""),
                            is_home_user=root.get("home", "0") == "1",
                            is_restricted=root.get("restricted", "0") == "1",
                        )

                        # Log performance
                        duration = (datetime.now() - start_time).total_seconds() * 1000
                        performance_logger.log_request_duration(
                            "plex_authenticate_user",
                            "GET",
                            duration,
                            response.status_code,
                        )

                        self.logger.info(f"Successfully authenticated user: {user.username}")
                        return user
                else:
                    self.logger.warning(f"Failed to authenticate user: {response.status_code}")
                    raise PlexAuthenticationError("Invalid Plex token")

        except PlexAuthenticationError:
            raise
        except httpx.TimeoutException:
            self.logger.error("Timeout authenticating user")
            raise PlexConnectionError("Plex service timeout during authentication")
        except httpx.RequestError as e:
            self.logger.error(f"Network error authenticating user: {e}")
            raise PlexConnectionError(f"Network error: {e}")
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse Plex XML response: {e}")
            raise PlexAuthenticationError("Invalid response from Plex")
        except Exception as e:
            self.logger.error(f"Unexpected error authenticating user: {e}")
            raise ExternalServiceError(f"Authentication failed: {e}")

        return None

    async def get_current_session(self, plex_token: str, username: str) -> Optional[SessionInfo]:
        """Get user's current playback session"""
        try:
            self.logger.debug(f"Getting current session for user: {username}")

            # Get sessions with server context
            sessions_with_servers = await self._get_all_user_sessions_with_server_context(
                plex_token
            )

            for session, server in sessions_with_servers:
                if session.username.lower() == username.lower():
                    self.logger.info(f"Found current session for user {username}")
                    # Set server context for file path resolution
                    setattr(session, "_server_context", server)
                    return session

            self.logger.debug(f"No current session found for user: {username}")
            return None

        except Exception as e:
            self.logger.error(f"Failed to get current session for {username}: {e}")
            raise SessionNotFoundError(f"Failed to retrieve current session: {e}")

    async def get_all_user_sessions(self, plex_token: str, username: str) -> List[SessionInfo]:
        """Get all user's playback sessions"""
        try:
            self.logger.debug(f"Getting all sessions for user: {username}")

            user_sessions = []

            # Get sessions with server context
            sessions_with_servers = await self._get_all_user_sessions_with_server_context(
                plex_token
            )

            for session, server in sessions_with_servers:
                if session.username.lower() == username.lower():
                    # Set server context for file path resolution
                    setattr(session, "_server_context", server)
                    user_sessions.append(session)

            self.logger.info(f"Found {len(user_sessions)} sessions for user {username}")
            return user_sessions

        except Exception as e:
            self.logger.error(f"Failed to get all sessions for {username}: {e}")
            raise SessionNotFoundError(f"Failed to retrieve user sessions: {e}")

    @with_plex_retry()
    async def _get_server_identity_from_token(self, token: str) -> Optional[PlexServer]:
        """Get server identity directly using an admin token"""
        try:
            self.logger.debug("Getting server identity using admin token")

            # First, try to get server list to find the server this token belongs to
            servers = await self._get_user_servers(token)

            if not servers:
                self.logger.warning("No servers found with provided token")
                return None

            # For an admin token, the first owned server is typically the right one
            for server in servers:
                if server.owned:
                    # Now get detailed server info using the identity endpoint
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        headers = self._get_headers(token)
                        headers["Accept"] = "application/json"

                        try:
                            # Try to get server identity for confirmation
                            identity_response = await client.get(
                                f"{server.url}/identity", headers=headers
                            )

                            if identity_response.status_code == 200:
                                identity_data = identity_response.json()
                                # Update server with confirmed identity
                                server.machine_identifier = identity_data.get(
                                    "MediaContainer", {}
                                ).get("machineIdentifier", server.machine_identifier)
                                self.logger.info(
                                    f"Identified server: {server.name} (ID: {server.machine_identifier})"
                                )
                                return server  # type: ignore[no-any-return]
                        except Exception as e:
                            self.logger.debug(f"Could not get identity from {server.url}: {e}")
                            # Still return the server even if identity check fails
                            return server  # type: ignore[no-any-return]

            # If no owned servers, return the first one
            if servers:
                self.logger.info(f"Using first available server: {servers[0].name}")
                return servers[0]  # type: ignore[no-any-return]

            return None

        except Exception as e:
            self.logger.error(f"Failed to get server identity from token: {e}")
            return None

    @with_plex_retry()
    async def _get_user_servers(self, token: str) -> List[PlexServer]:
        """Get list of Plex servers the user has access to"""
        start_time = datetime.now()

        try:
            self.logger.debug("Fetching user's Plex servers")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/pms/servers", headers=self._get_headers(token)
                )

                if response.status_code == 200:
                    # Plex returns XML for servers list
                    xml_content = response.text
                    root = ET.fromstring(xml_content)

                    servers = []
                    server_elements = root.findall("Server")

                    for server_element in server_elements:
                        server_name = server_element.get("name", "")

                        # Parse server connections
                        connections = []
                        for connection_element in server_element.findall("Connection"):
                            connection = PlexServerConnection(
                                protocol=connection_element.get("protocol", "http"),
                                address=connection_element.get("address", ""),
                                port=int(connection_element.get("port", 32400)),
                                uri=connection_element.get("uri", ""),
                                local=connection_element.get("local", "0") == "1",
                            )
                            connections.append(connection)

                        # Create server object
                        server = PlexServer(
                            name=server_name,
                            machine_identifier=server_element.get("machineIdentifier", ""),
                            host=server_element.get("host", ""),
                            port=int(server_element.get("port", 32400)),
                            version=server_element.get("version", ""),
                            scheme=server_element.get("scheme", "http"),
                            connections=connections,
                            owned=server_element.get("owned", "1") == "1",
                            synced=server_element.get("synced", "0") == "1",
                            access_token=server_element.get("accessToken"),
                        )
                        servers.append(server)

                    # Log performance
                    duration = (datetime.now() - start_time).total_seconds() * 1000
                    performance_logger.log_request_duration(
                        "plex_get_servers", "GET", duration, response.status_code
                    )

                    self.logger.info(f"Retrieved {len(servers)} Plex servers")
                    return servers
                else:
                    self.logger.warning(f"Failed to get servers: {response.status_code}")

        except httpx.TimeoutException:
            self.logger.error("Timeout getting Plex servers")
            raise PlexConnectionError("Plex service timeout getting servers")
        except httpx.RequestError as e:
            self.logger.error(f"Network error getting servers: {e}")
            raise PlexConnectionError(f"Network error: {e}")
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse servers XML response: {e}")
            raise PlexConnectionError("Invalid response from Plex")
        except Exception as e:
            self.logger.error(f"Unexpected error getting servers: {e}")
            raise ExternalServiceError(f"Failed to get servers: {e}")

        return []

    @with_plex_retry()
    async def _get_server_sessions(self, token: str, server: PlexServer) -> List[SessionInfo]:
        """Get all current sessions from a specific Plex server"""
        try:
            self.logger.debug(f"Getting sessions from server: {server.name}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Use server-specific token for shared servers, user token for owned servers
                token_to_use = (
                    server.access_token if server.access_token and not server.owned else token
                )

                # Force JSON response
                headers = self._get_headers(token_to_use)
                headers["Accept"] = "application/json"

                response = await client.get(f"{server.url}/status/sessions", headers=headers)

                if response.status_code == 200:
                    content = response.text

                    if not content.strip():
                        return []

                    try:
                        json_data = json.loads(content)
                        sessions = self._parse_sessions_from_json(json_data)
                        self.logger.debug(f"Found {len(sessions)} sessions on server {server.name}")
                        return sessions
                    except json.JSONDecodeError:
                        self.logger.warning(f"Failed to parse JSON from server {server.name}")
                        return []
                else:
                    self.logger.warning(
                        f"Server {server.name} returned {response.status_code} for session request"
                    )
                    if response.status_code == 403:
                        self.logger.info(
                            "Consider using CLIPFORGE_PLEX_SERVER_TOKEN with admin privileges"
                        )

        except httpx.TimeoutException:
            self.logger.warning(f"Timeout getting sessions from server {server.name}")
        except httpx.RequestError as e:
            self.logger.warning(f"Network error getting sessions from server {server.name}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error getting sessions from server {server.name}: {e}")

        return []

    async def _get_all_user_sessions_with_server_context(
        self, token: str
    ) -> List[Tuple[SessionInfo, PlexServer]]:
        """Get sessions from user's servers with server context"""
        sessions_with_servers = []

        # Check if we have a server token configured
        server_token = (
            settings.plex_server_token if hasattr(settings, "plex_server_token") else None
        )

        # Priority: server token > server name > first available
        if server_token:
            # Use server token to get server identity and all sessions
            self.logger.info("Using configured server token for session fetching")
            server = await self._get_server_identity_from_token(server_token)

            if server:
                try:
                    # Use the server token to get all sessions (admin access)
                    server_sessions = await self._get_server_sessions(server_token, server)
                    for session in server_sessions:
                        sessions_with_servers.append((session, server))
                except Exception as e:
                    self.logger.warning(f"Failed to get sessions from server {server.name}: {e}")
            else:
                self.logger.error("Could not identify server from provided token")
                return []
        else:
            # Fall back to original logic if no server token
            target_server_name = (
                settings.plex_server_name if hasattr(settings, "plex_server_name") else None
            )

            # Get user's servers using their token
            servers = await self._get_user_servers(token)

            # Filter to target server if specified
            if target_server_name:
                available_names = [s.name for s in servers]
                servers = [s for s in servers if s.name == target_server_name]
                if not servers:
                    self.logger.warning(
                        f"Target server '{target_server_name}' not found. Available: {available_names}"
                    )
                    return []

            # Get sessions from servers using user token
            for server in servers:
                try:
                    server_sessions = await self._get_server_sessions(token, server)
                    for session in server_sessions:
                        sessions_with_servers.append((session, server))
                except Exception as e:
                    self.logger.warning(f"Failed to get sessions from server {server.name}: {e}")
                    continue

        return sessions_with_servers

    def _parse_sessions_from_json(self, json_data: Dict[str, Any]) -> List[SessionInfo]:
        """Parse sessions from JSON response"""
        sessions = []

        try:
            media_container = json_data.get("MediaContainer", {})
            metadata_list = media_container.get("Metadata", [])

            for metadata in metadata_list:
                session = self._parse_session_from_json(metadata)
                if session:
                    sessions.append(session)

        except Exception as e:
            self.logger.error(f"Failed to parse sessions JSON: {e}")

        return sessions

    def _parse_session_from_json(self, metadata: Dict[str, Any]) -> Optional[SessionInfo]:
        """Parse a session from JSON metadata"""
        try:
            session_data = metadata.get("Session", {})
            if not session_data:
                return None

            # Get user information
            user_data = metadata.get("User", {})
            username = user_data.get("title", "")
            user_id = str(user_data.get("id", ""))

            # Parse player information
            player_data = metadata.get("Player", {})
            player = self._parse_player_from_json(player_data)

            # Parse session information
            session_info = self._parse_session_info_from_json(session_data)

            # Get media information
            media = self._parse_media_from_json(metadata)
            if not media:
                return None

            # Get session key
            session_key = str(
                session_data.get("id", metadata.get("sessionKey", metadata.get("key", "")))
            )

            # Use player state as primary source
            player_state = player_data.get("state", "stopped")
            state = player_state or session_info.state or "stopped"
            session_info.state = state

            # Get view offset
            view_offset = session_info.view_offset or int(metadata.get("viewOffset", 0))
            session_info.view_offset = view_offset

            # Calculate progress percentage
            if media.duration and media.duration > 0:
                session_info.progress_percent = (view_offset / media.duration) * 100

            # Extract original file info from media streams
            original_file_info = None
            if media.media_streams:
                for stream in media.media_streams:
                    if stream.parts:
                        for part in stream.parts:
                            if part.file:
                                original_file_info = OriginalFileInfo(file_path=part.file)
                                self.logger.debug(f"Extracted file path from session: {part.file}")
                                break
                    if original_file_info:
                        break

            return SessionInfo(
                session_key=session_key,
                user_id=user_id,
                username=username,
                media=media,
                player=player,
                session=session_info,
                original_file_info=original_file_info,
            )

        except Exception as e:
            self.logger.error(f"Failed to parse session from JSON: {e}")
            return None

    def _parse_player_from_json(self, player_data: Dict[str, Any]) -> PlayerInfo:
        """Parse player information from JSON"""
        return PlayerInfo(
            machine_identifier=player_data.get("machineIdentifier", ""),
            product=player_data.get("product", ""),
            platform=player_data.get("platform", ""),
            platform_version=player_data.get("platformVersion", ""),
            device=player_data.get("device", ""),
            model=player_data.get("model", ""),
            vendor=player_data.get("vendor"),
            version=player_data.get("version", ""),
            address=player_data.get("address", ""),
            port=player_data.get("port"),
            protocol=player_data.get("protocol"),
            protocol_version=player_data.get("protocolVersion"),
            protocol_capabilities=player_data.get("protocolCapabilities"),
            title=player_data.get("title", ""),
            device_class=player_data.get("deviceClass"),
            profile=player_data.get("profile"),
            remote_public_address=player_data.get("remotePublicAddress"),
            local=player_data.get("local"),
            relay=player_data.get("relay"),
            secure=player_data.get("secure"),
            user_id=player_data.get("userID"),
        )

    def _parse_session_info_from_json(self, session_data: Dict[str, Any]) -> PlexSessionInfo:
        """Parse session information from JSON"""
        return PlexSessionInfo(
            id=str(session_data.get("id", "")),
            bandwidth=session_data.get("bandwidth"),
            location=session_data.get("location"),
            state=session_data.get("state", "stopped"),
            view_offset=int(session_data.get("viewOffset", 0)),
            started_at=self._parse_timestamp(session_data.get("startedAt")),
            last_viewed_at=self._parse_timestamp(session_data.get("lastViewedAt")),
            transcoding=session_data.get("transcoding"),
            container=session_data.get("container"),
            video_decision=session_data.get("videoDecision"),
            audio_decision=session_data.get("audioDecision"),
            subtitle_decision=session_data.get("subtitleDecision"),
            throttled=session_data.get("throttled"),
            synced_version=session_data.get("syncedVersion"),
            synced_version_profile=session_data.get("syncedVersionProfile"),
            max_allowed_resolution=session_data.get("maxAllowedResolution"),
            audio_codec=session_data.get("audioCodec"),
            video_codec=session_data.get("videoCodec"),
            protocol=session_data.get("protocol"),
            mde=session_data.get("mde"),
        )

    def _parse_media_from_json(self, metadata: Dict[str, Any]) -> Optional[MediaInfo]:
        """Parse media information from JSON metadata"""
        try:
            # Parse media streams
            media_streams = self._parse_media_streams_from_json(metadata.get("Media", []))

            # Parse GUIDs
            guids = self._parse_guids_from_json(metadata.get("Guid", []))

            return MediaInfo(
                key=metadata.get("key", ""),
                rating_key=metadata.get("ratingKey"),
                guid=metadata.get("guid"),
                guids=guids,
                title=metadata.get("title", ""),
                media_type=metadata.get("type", ""),
                duration=metadata.get("duration"),
                thumb=metadata.get("thumb"),
                art=metadata.get("art"),
                banner=metadata.get("banner"),
                theme=metadata.get("theme"),
                year=metadata.get("year"),
                originally_available_at=metadata.get("originallyAvailableAt"),
                added_at=metadata.get("addedAt"),
                updated_at=metadata.get("updatedAt"),
                last_viewed_at=metadata.get("lastViewedAt"),
                view_count=metadata.get("viewCount"),
                skip_count=metadata.get("skipCount"),
                rating=metadata.get("rating"),
                audience_rating=metadata.get("audienceRating"),
                content_rating=metadata.get("contentRating"),
                studio=metadata.get("studio"),
                tag_line=metadata.get("tagline"),
                summary=metadata.get("summary"),
                show_title=metadata.get("grandparentTitle"),
                grandparent_key=metadata.get("grandparentKey"),
                grandparent_rating_key=metadata.get("grandparentRatingKey"),
                grandparent_guid=metadata.get("grandparentGuid"),
                grandparent_thumb=metadata.get("grandparentThumb"),
                grandparent_art=metadata.get("grandparentArt"),
                grandparent_theme=metadata.get("grandparentTheme"),
                parent_title=metadata.get("parentTitle"),
                parent_key=metadata.get("parentKey"),
                parent_rating_key=metadata.get("parentRatingKey"),
                parent_guid=metadata.get("parentGuid"),
                parent_thumb=metadata.get("parentThumb"),
                season_number=metadata.get("parentIndex"),
                episode_number=metadata.get("index"),
                media_streams=media_streams,
            )

        except Exception as e:
            self.logger.error(f"Failed to parse media from JSON: {e}")
            return None

    def _parse_media_streams_from_json(
        self, media_data: List[Dict[str, Any]]
    ) -> List[PlexStreamMedia]:
        """Parse media streams from JSON"""
        streams = []
        for stream_data in media_data:
            parts = self._parse_parts_from_json(stream_data.get("Part", []))

            stream = PlexStreamMedia(
                id=str(stream_data.get("id", "")),
                duration=stream_data.get("duration"),
                bitrate=stream_data.get("bitrate"),
                parts=parts,
            )
            streams.append(stream)
        return streams

    def _parse_parts_from_json(self, parts_data: List[Dict[str, Any]]) -> List[PlexStreamPart]:
        """Parse media parts from JSON"""
        parts = []
        for part_data in parts_data:
            part = PlexStreamPart(
                id=str(part_data.get("id", "")),
                key=part_data.get("key"),
                duration=part_data.get("duration"),
                file=part_data.get("file"),
            )
            parts.append(part)
        return parts

    def _parse_guids_from_json(self, guids_data: List[Dict[str, Any]]) -> List[PlexGuid]:
        """Parse GUIDs from JSON"""
        guids = []
        for guid_data in guids_data:
            if guid_data.get("id"):
                guids.append(PlexGuid(id=guid_data["id"]))
        return guids

    def _parse_timestamp(self, timestamp_value: Any) -> Optional[datetime]:
        """Parse timestamp from various Plex formats"""
        if not timestamp_value:
            return None

        try:
            if isinstance(timestamp_value, (int, float)):
                return datetime.fromtimestamp(timestamp_value)
            elif isinstance(timestamp_value, str):
                try:
                    return datetime.fromtimestamp(float(timestamp_value))
                except ValueError:
                    return datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        except Exception as e:
            self.logger.warning(f"Failed to parse timestamp {timestamp_value}: {e}")

        return None

    @with_plex_retry()
    async def get_media_file_info(
        self, token: str, server: PlexServer, media_key: str
    ) -> Optional[OriginalFileInfo]:
        """Get original file information for a media item"""
        try:
            self.logger.debug(f"Getting media file info for key: {media_key}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = self._get_headers(token)
                headers["Accept"] = "application/json"

                response = await client.get(f"{server.url}{media_key}", headers=headers)

                if response.status_code == 200:
                    json_data = response.json()
                    media_container = json_data.get("MediaContainer", {})
                    metadata_list = media_container.get("Metadata", [])

                    if metadata_list:
                        metadata = metadata_list[0]
                        media_list = metadata.get("Media", [])

                        if media_list:
                            media = media_list[0]
                            part_list = media.get("Part", [])

                            if part_list:
                                part = part_list[0]
                                file_path = part.get("file")

                                if file_path:
                                    self.logger.debug(f"Found file path: {file_path}")
                                    return OriginalFileInfo(file_path=file_path)
                else:
                    self.logger.warning(
                        f"Failed to get media file info: {response.status_code} for {media_key}"
                    )
                    if response.status_code == 401:
                        self.logger.error(
                            f"Authentication failed - token may not have sufficient permissions. Token used: {token[:5]}...{token[-5:] if len(token) > 10 else ''}"
                        )
                    elif response.status_code == 404:
                        self.logger.error(f"Media not found: {media_key}")

            self.logger.warning(f"No file path found for media key: {media_key}")
            return None

        except Exception as e:
            self.logger.error(f"Failed to get media file info: {e}")
            return None
