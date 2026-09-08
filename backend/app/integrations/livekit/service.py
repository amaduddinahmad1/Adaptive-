"""
LiveKit Service implementation.
"""
import logging
from typing import Optional

from livekit import api

from app.integrations.livekit.config import LiveKitConfig

logger = logging.getLogger(__name__)


class LiveKitService:
    def __init__(self, config: LiveKitConfig):
        self.config = config
        if not self.config.is_valid():
            logger.warning("LiveKit config is incomplete. Mock mode enabled.")

    def is_mock_mode(self) -> bool:
        return not self.config.is_valid()

    def _client(self) -> api.LiveKitAPI:
        return api.LiveKitAPI(
            self.config.url,
            self.config.api_key,
            self.config.api_secret,
        )

    async def create_room(self, room_name: str) -> dict:
        """Create a new room."""
        if self.is_mock_mode():
            logger.info(f"Creating mock LiveKit room: {room_name}")
            return {"name": room_name, "sid": f"mock_rm_{room_name}"}

        lkapi = self._client()
        try:
            room = await lkapi.room.create_room(api.CreateRoomRequest(name=room_name))
            return {
                "name": getattr(room, "name", None) or room_name,
                "sid": getattr(room, "sid", "") or "",
            }
        except Exception:
            logger.warning(
                "LiveKit create_room failed for %s; continuing so the client can still join",
                room_name,
                exc_info=True,
            )
            return {"name": room_name, "sid": ""}
        finally:
            await lkapi.aclose()

    def generate_token(self, room_name: str, participant_identity: str) -> str:
        """Generate access token for a participant."""
        if self.is_mock_mode():
            logger.info(f"Generating mock LiveKit token for {participant_identity} in {room_name}")
            return f"mock_token_{room_name}_{participant_identity}"

        return (
            api.AccessToken(self.config.api_key, self.config.api_secret)
            .with_identity(participant_identity)
            .with_name(participant_identity)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
            .to_jwt()
        )

    async def delete_room(self, room_name: str) -> bool:
        """Delete a room."""
        if self.is_mock_mode():
            logger.info(f"Deleting mock LiveKit room: {room_name}")
            return True

        lkapi = self._client()
        try:
            await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
            return True
        except Exception:
            logger.warning("LiveKit delete_room failed for %s", room_name, exc_info=True)
            return False
        finally:
            await lkapi.aclose()

    def get_room_info(self, room_name: str) -> Optional[dict]:
        """Get room information."""
        logger.info(f"Fetching mock LiveKit room info: {room_name}")
        return {"name": room_name, "sid": f"mock_rm_{room_name}", "num_participants": 0}
