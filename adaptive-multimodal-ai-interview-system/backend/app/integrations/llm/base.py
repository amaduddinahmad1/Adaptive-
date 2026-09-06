from abc import ABC, abstractmethod
from typing import Any, Optional


class LLMProviderError(Exception):
    """Raised when an LLM provider cannot complete a generation request."""


class LLMProvider(ABC):
    """Provider-agnostic interface for schema-constrained text generation."""

    @abstractmethod
    def generate_structured(
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: Any,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate schema-constrained JSON and return the response text."""
        raise NotImplementedError
