"""
Factory for STT Providers.
"""
import logging
import os
import threading
from typing import Dict, Optional, Type

from app.integrations.stt.base import STTProvider
from app.integrations.stt.mock_provider import MockSTTProvider
from app.integrations.stt.providers.whisper_local import WhisperLocalSTTProvider

logger = logging.getLogger(__name__)

_DEFAULT_PROVIDER = "whisper_local"


class STTProviderFactory:
    _providers: Dict[str, Type[STTProvider]] = {
        "mock": MockSTTProvider,
        "whisper_local": WhisperLocalSTTProvider,
    }
    _instances: Dict[str, STTProvider] = {}
    _init_lock = threading.Lock()

    @classmethod
    def register_provider(cls, name: str, provider_class: Type[STTProvider]):
        """Register a new provider."""
        cls._providers[name] = provider_class

    @classmethod
    def get_provider(cls, provider_name: Optional[str] = None) -> STTProvider:
        """Get an instance of a provider by name.

        When ``provider_name`` is omitted, uses ``STT_PROVIDER`` or whisper_local.
        Instances are cached so the Whisper model is loaded at most once.
        """
        raw = provider_name if provider_name is not None else os.getenv("STT_PROVIDER", _DEFAULT_PROVIDER)
        name = (raw or _DEFAULT_PROVIDER).strip().lower() or _DEFAULT_PROVIDER
        cached = cls._instances.get(name)
        if cached is not None:
            return cached
        with cls._init_lock:
            cached = cls._instances.get(name)
            if cached is not None:
                return cached
            provider_class = cls._providers.get(name)
            if not provider_class:
                raise ValueError(f"Unknown STT provider: {provider_name or name}")
            instance = provider_class()
            cls._instances[name] = instance
            return instance


def warmup_whisper_model() -> None:
    """Load the local Whisper weights in the worker process before LiveKit connect."""
    try:
        provider = STTProviderFactory.get_provider("whisper_local")
        ensure = getattr(provider, "_ensure_model", None)
        if callable(ensure):
            ensure()
    except Exception:
        logger.warning("Whisper STT prewarm skipped", exc_info=True)
