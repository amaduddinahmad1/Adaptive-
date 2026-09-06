"""
Factory for STT Providers.
"""
from typing import Dict, Type
from app.integrations.stt.base import STTProvider
from app.integrations.stt.mock_provider import MockSTTProvider

class STTProviderFactory:
    _providers: Dict[str, Type[STTProvider]] = {
        "mock": MockSTTProvider
    }

    @classmethod
    def register_provider(cls, name: str, provider_class: Type[STTProvider]):
        """Register a new provider."""
        cls._providers[name] = provider_class

    @classmethod
    def get_provider(cls, provider_name: str) -> STTProvider:
        """Get an instance of a provider by name."""
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown STT provider: {provider_name}")
        return provider_class()
