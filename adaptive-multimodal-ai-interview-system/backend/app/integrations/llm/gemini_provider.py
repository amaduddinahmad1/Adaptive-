import os
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.integrations.llm.base import LLMProvider, LLMProviderError

load_dotenv()

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"


class GeminiProvider(LLMProvider):
    """Google Gemini implementation of the provider-agnostic LLM interface."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[genai.Client] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.client = client

    def _ensure_client(self) -> genai.Client:
        if self.client is None:
            if not self.api_key:
                raise LLMProviderError(
                    "GEMINI_API_KEY is not set. Set the environment variable or "
                    "pass api_key / client to GeminiProvider."
                )
            self.client = genai.Client(api_key=self.api_key)
        return self.client

    def generate_structured(
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: Any,
        temperature: Optional[float] = None,
    ) -> str:
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        }
        if temperature is not None:
            config_kwargs["temperature"] = temperature

        try:
            response = self._ensure_client().models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except APIError as err:
            raise LLMProviderError(f"Gemini API error during generation: {err}") from err
        except Exception as err:
            raise LLMProviderError(f"Unexpected error calling Gemini: {err}") from err

        response_text = getattr(response, "text", None)
        if not response_text or not response_text.strip():
            raise LLMProviderError("Gemini model returned an empty response.")
        return response_text
