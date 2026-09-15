"""
app/integrations/llm/xai_provider.py

xAI Grok implementation of the provider-agnostic LLM interface, used as the
fallback provider when Gemini is unavailable (see factory.py).

Uses the official xai-sdk rather than hand-rolled HTTP against
https://api.x.ai/v1: xai-sdk's chat.create(response_format=<PydanticModel>)
handles converting a Pydantic model into xAI's required strict JSON-schema
request shape, which is real, error-prone work otherwise (xAI's own docs
warn that a malformed schema envelope is rejected server-side with an
unclear error).

Error handling mirrors gemini_provider.py's discipline exactly: catch the
SDK's known error type plus a bare Exception, and always re-raise as
LLMProviderError via `from err` so the original exception survives on
`.__cause__` for classification (see fallback_provider.py / factory.py).

xai-sdk is grpc-based under the hood -- confirmed empirically (not
assumed) by triggering a real auth failure against the API: the SDK does
not wrap grpc's exceptions in a custom error type, it raises
grpc.RpcError subclasses directly (e.g. grpc._channel._InactiveRpcError),
exposing a `.code()` method returning a grpc.StatusCode enum member
(e.g. UNAVAILABLE for a transient server-side failure, INVALID_ARGUMENT
for a bad API key). factory.py's transience check for this provider, if
ever used as the primary, would check `err.__cause__.code() ==
grpc.StatusCode.UNAVAILABLE`, not just isinstance(err.__cause__, grpc.RpcError)
-- a bad request is also a grpc.RpcError, but not a transient one.
"""
import os
from typing import Any, Optional

import grpc
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import system, user

from app.integrations.llm.base import LLMProvider, LLMProviderError

load_dotenv()

DEFAULT_XAI_MODEL = "grok-4.6"


class XAIProvider(LLMProvider):
    """xAI Grok implementation of the provider-agnostic LLM interface."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Client] = None,
    ):
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        self.model = model or os.getenv("XAI_MODEL", DEFAULT_XAI_MODEL)
        self.client = client

    def _ensure_client(self) -> Client:
        if self.client is None:
            if not self.api_key:
                raise LLMProviderError(
                    "XAI_API_KEY is not set. Set the environment variable or "
                    "pass api_key / client to XAIProvider."
                )
            self.client = Client(api_key=self.api_key)
        return self.client

    def generate_structured(
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: Any,
        temperature: Optional[float] = None,
    ) -> str:
        try:
            chat = self._ensure_client().chat.create(
                model=self.model,
                response_format=response_schema,
                temperature=temperature,
            )
            chat.append(system(system_instruction))
            chat.append(user(prompt))
            response = chat.sample()
        except grpc.RpcError as err:
            raise LLMProviderError(f"xAI API error during generation: {err}") from err
        except Exception as err:
            raise LLMProviderError(f"Unexpected error calling xAI: {err}") from err

        response_text = getattr(response, "content", None)
        if not response_text or not response_text.strip():
            raise LLMProviderError("xAI model returned an empty response.")
        return response_text
