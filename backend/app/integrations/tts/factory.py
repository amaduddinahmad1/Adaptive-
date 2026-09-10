"""
Factory for TTS Providers.
"""
import logging
import os
from typing import Dict, Optional, Type

from app.integrations.tts.base import TTSProvider
from app.integrations.tts.mock_provider import MockTTSProvider
from app.integrations.tts.providers.elevenlabs_tts import ElevenLabsTTSProvider, TTSProviderError
from app.integrations.tts.providers.local_tts import LocalTTSProvider
from app.schemas.tts import TTSConfig, TTSResult

logger = logging.getLogger(__name__)

_DEFAULT_PROVIDER = "elevenlabs"
_PRIMARY_PROVIDER = "elevenlabs_tts"
_FALLBACK_PROVIDER = "local_tts"

_CANONICAL_NAMES = {
    "elevenlabs_tts": "elevenlabs",
    "local_tts": "local_fallback",
}


class TTSProviderFactory:
    _providers: Dict[str, Type[TTSProvider]] = {
        "mock": MockTTSProvider,
        "elevenlabs": ElevenLabsTTSProvider,
        "local_fallback": LocalTTSProvider,
    }
    _instances: Dict[str, TTSProvider] = {}

    @classmethod
    def register_provider(cls, name: str, provider_class: Type[TTSProvider]):
        """Register a new provider."""
        cls._providers[name] = provider_class

    @classmethod
    def get_provider(cls, provider_name: Optional[str] = None) -> TTSProvider:
        """Get an instance of a provider by name.

        When ``provider_name`` is omitted, uses ``TTS_PROVIDER`` or elevenlabs.
        ``elevenlabs_tts`` and ``local_tts`` are accepted as aliases.
        Successful instances are cached; failed construction is not.
        """
        raw = provider_name if provider_name is not None else os.getenv("TTS_PROVIDER", _DEFAULT_PROVIDER)
        name = _canonical_name(raw or _DEFAULT_PROVIDER)
        cached = cls._instances.get(name)
        if cached is not None:
            return cached
        provider_class = cls._providers.get(name)
        if not provider_class:
            raise ValueError(f"Unknown TTS provider: {provider_name or name}")
        instance = provider_class()
        cls._instances[name] = instance
        return instance

    @classmethod
    async def synthesize_with_fallback(cls, text: str, config: TTSConfig) -> TTSResult:
        """Synthesize with ElevenLabs, then local MMS-TTS on TTSProviderError."""
        try:
            primary = cls.get_provider(_PRIMARY_PROVIDER)
            result = await primary.synthesize(text, config)
            logger.info("TTS request served by provider '%s'", result.provider)
            return result
        except TTSProviderError as primary_error:
            logger.warning(
                "TTS provider '%s' failed (%s); falling back to '%s'",
                _PRIMARY_PROVIDER,
                primary_error,
                _FALLBACK_PROVIDER,
            )
            try:
                fallback = cls.get_provider(_FALLBACK_PROVIDER)
                result = await fallback.synthesize(text, config)
            except Exception as fallback_error:
                raise TTSProviderError(
                    "TTS failed with elevenlabs "
                    f"({primary_error}) and local_tts ({fallback_error})"
                ) from fallback_error
            logger.info("TTS request served by provider '%s'", result.provider)
            return result


def _canonical_name(provider_name: str) -> str:
    name = provider_name.strip().lower() or _DEFAULT_PROVIDER
    return _CANONICAL_NAMES.get(name, name)
