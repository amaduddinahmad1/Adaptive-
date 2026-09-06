"""
Session Manager for Voice Interviews.
"""
from typing import Dict, Optional, List
from app.schemas.voice_session import VoiceSessionSchema, VoiceSessionUpdate

class SessionManager:
    def __init__(self):
        # In-memory session store
        self._sessions: Dict[str, VoiceSessionSchema] = {}

    def create_session(self, session: VoiceSessionSchema) -> VoiceSessionSchema:
        """Store a new session."""
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[VoiceSessionSchema]:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    def update_session(self, session_id: str, update_data: VoiceSessionUpdate) -> Optional[VoiceSessionSchema]:
        """Update an existing session."""
        session = self.get_session(session_id)
        if not session:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(session, key, value)
            
        return session

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
        
    def list_sessions(self) -> List[VoiceSessionSchema]:
        """List all active sessions."""
        return list(self._sessions.values())
