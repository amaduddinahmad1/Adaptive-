"""
Factory for TTS Providers.
"""
from typing import Dict, Type
from app.integrations.tts.base import TTSProvider
from app.integrations.tts.mock_provider import MockTTSProvider

class TTSProviderFactory:
    _providers: Dict[str, Type[TTSProvider]] = {
        "mock": MockTTSProvider
    }

    @classmethod
    def register_provider(cls, name: str, provider_class: Type[TTSProvider]):
        """Register a new provider."""
        cls._providers[name] = provider_class

    @classmethod
    def get_provider(cls, provider_name: str) -> TTSProvider:
        """Get an instance of a provider by name."""
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown TTS provider: {provider_name}")
        return provider_class()
