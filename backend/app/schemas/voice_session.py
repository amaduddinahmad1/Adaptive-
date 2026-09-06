"""
Voice session schemas for the Adaptive Multimodal AI Interview System.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class InterviewStatus(str, Enum):
    PENDING = "PENDING"
    CONNECTING = "CONNECTING"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ConnectionStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"

class VoiceSessionBase(BaseModel):
    candidate_id: str
    job_id: str
    language: str = "en"

class VoiceSessionCreate(VoiceSessionBase):
    pass

class VoiceSessionUpdate(BaseModel):
    interview_status: Optional[InterviewStatus] = None
    connection_status: Optional[ConnectionStatus] = None
    current_question_id: Optional[str] = None
    current_question: Optional[str] = None

class VoiceSessionSchema(VoiceSessionBase):
    session_id: str
    interview_status: InterviewStatus = InterviewStatus.PENDING
    connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    current_question_id: Optional[str] = None
    current_question: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        from_attributes = True
