"""
Speech-to-Text (STT) schemas.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel

class STTConfig(BaseModel):
    provider: str
    language: str
    model: Optional[str] = None
    sample_rate: int = 16000
    encoding: str = 'LINEAR16'

class STTResult(BaseModel):
    text: str
    language: str
    confidence: float
    processing_time_ms: float
    provider: str
    raw_metadata: Optional[Dict[str, Any]] = None
