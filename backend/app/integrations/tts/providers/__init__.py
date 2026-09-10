"""
TTS provider implementations.
"""
from app.integrations.tts.providers.elevenlabs_tts import ElevenLabsTTSProvider
from app.integrations.tts.providers.local_tts import LocalTTSProvider

__all__ = ["ElevenLabsTTSProvider", "LocalTTSProvider"]
