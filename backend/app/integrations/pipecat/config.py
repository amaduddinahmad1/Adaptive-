"""
Pipecat configuration.
"""
from pydantic import BaseModel

class PipecatConfig(BaseModel):
    sample_rate: int = 16000
    chunk_size: int = 1024
    enable_vad: bool = True
