"""
LiveKit Service implementation (placeholder).
"""
import logging
from typing import Optional
from app.integrations.livekit.config import LiveKitConfig

logger = logging.getLogger(__name__)

class LiveKitService:
    def __init__(self, config: LiveKitConfig):
        self.config = config
        if not self.config.is_valid():
            logger.warning("LiveKit config is incomplete. Mock mode enabled.")

    def create_room(self, room_name: str) -> dict:
        """Create a new room."""
        logger.info(f"Creating mock LiveKit room: {room_name}")
        return {"name": room_name, "sid": f"mock_rm_{room_name}"}

    def generate_token(self, room_name: str, participant_identity: str) -> str:
        """Generate access token for a participant."""
        logger.info(f"Generating mock LiveKit token for {participant_identity} in {room_name}")
        return f"mock_token_{room_name}_{participant_identity}"

    def delete_room(self, room_name: str) -> bool:
        """Delete a room."""
        logger.info(f"Deleting mock LiveKit room: {room_name}")
        return True

    def get_room_info(self, room_name: str) -> Optional[dict]:
        """Get room information."""
        logger.info(f"Fetching mock LiveKit room info: {room_name}")
        return {"name": room_name, "sid": f"mock_rm_{room_name}", "num_participants": 0}
