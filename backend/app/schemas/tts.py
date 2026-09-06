"""
Text-to-Speech (TTS) schemas.
"""
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel

class SupportedLanguage(str, Enum):
    ENGLISH = "en"
    URDU = "ur"
    ROMAN_URDU = "ru"

class TTSConfig(BaseModel):
    provider: str
    language: str
    voice_id: Optional[str] = None
    model: Optional[str] = None
    speed: float = 1.0
    output_format: str = "wav"

class TTSResult(BaseModel):
    audio_data: bytes
    audio_format: str
    language: str
    processing_time_ms: float
    provider: str
    sample_rate: int
    raw_metadata: Optional[Dict[str, Any]] = None
