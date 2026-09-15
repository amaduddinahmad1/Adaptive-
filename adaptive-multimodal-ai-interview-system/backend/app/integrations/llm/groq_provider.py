"""
app/integrations/llm/groq_provider.py

Groq-hosted openai/gpt-oss-120b implementation of the provider-agnostic LLM
interface -- the third link in the Gemini -> xAI -> Groq fallback chain,
added because Groq's free tier needs no billing (unlike xAI, which needs
credits this account doesn't currently have).

Uses the official `groq` Python SDK rather than the OpenAI-compatible HTTP
endpoint (https://api.groq.com/openai/v1) directly: the SDK ships a clean,
typed exception hierarchy confirmed empirically by triggering a real auth
failure --

    GroqError -> APIError -> APIStatusError -> AuthenticationError (401),
                                                RateLimitError (429),
                                                InternalServerError (5xx), etc.

each carrying a real `.status_code` -- much better-suited to transience
classification than xAI's raw grpc.RpcError. Groq wants the JSON Schema
dict itself (response_schema.model_json_schema()), not a bare Pydantic
class the way xai-sdk accepts -- confirmed via Groq's structured-outputs
docs, not assumed.

Error handling mirrors gemini_provider.py/xai_provider.py's discipline:
catch the SDK's known error type plus a bare Exception, always re-raise as
LLMProviderError via `from err` so the original exception survives on
`.__cause__` for classification (see fallback_provider.py / factory.py).
Only InternalServerError (5xx) is treated as transient for this chain --
RateLimitError (429) is a structurally different failure class and is
deliberately not bundled in as "transient" here.

Real bug found and fixed after this provider first shipped: Groq's strict
structured-output mode rejects any schema unless EVERY object within it --
the root schema itself, and every entry under $defs for a nested Pydantic
model -- explicitly sets `additionalProperties: false`. Confirmed live
against the real API: AnswerRubricScores (a completely flat schema, no
nesting at all) failed with `additionalProperties:false must be set on
every object` at schema_path '$' -- the root object itself, not a nested
one. Pydantic's model_json_schema() never sets this anywhere, at any
level, by default (checked its signature -- no built-in option for it), so
_enforce_additional_properties_false() walks the schema recursively
(root, every $defs entry, and anything reachable through
properties/items/anyOf/oneOf/allOf) and sets it explicitly wherever an
object schema is missing it. This is Groq-specific: Gemini and xAI have
worked correctly all along without this treatment, so the walker lives
here rather than as a shared utility applied to every provider.
"""
import os
from typing import Any, Optional

from dotenv import load_dotenv
from groq import Groq, GroqError

from app.integrations.llm.base import LLMProvider, LLMProviderError

load_dotenv()

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def _enforce_additional_properties_false(schema: dict) -> dict:
    """
    Recursively sets additionalProperties: false on every object schema
    reachable from `schema` -- the schema itself, every entry under $defs,
    and anything nested through properties/items/anyOf/oneOf/allOf.
    Mutates and returns the same dict (model_json_schema() already returns
    a fresh dict on every call, so in-place mutation is safe here).
    """
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "additionalProperties" not in node:
                node["additionalProperties"] = False
            for key in ("properties", "$defs"):
                for value in node.get(key, {}).values():
                    walk(value)
            if "items" in node:
                walk(node["items"])
            for key in ("anyOf", "oneOf", "allOf"):
                for value in node.get(key, []):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return schema


class GroqProvider(LLMProvider):
    """Groq-hosted implementation of the provider-agnostic LLM interface."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Groq] = None,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.client = client

    def _ensure_client(self) -> Groq:
        if self.client is None:
            if not self.api_key:
                raise LLMProviderError(
                    "GROQ_API_KEY is not set. Set the environment variable or "
                    "pass api_key / client to GroqProvider."
                )
            self.client = Groq(api_key=self.api_key)
        return self.client

    def generate_structured(
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: Any,
        temperature: Optional[float] = None,
    ) -> str:
        request_kwargs: dict = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "strict": True,
                    "schema": _enforce_additional_properties_false(response_schema.model_json_schema()),
                },
            },
        )
        if temperature is not None:
            request_kwargs["temperature"] = temperature

        try:
            response = self._ensure_client().chat.completions.create(**request_kwargs)
        except GroqError as err:
            raise LLMProviderError(f"Groq API error during generation: {err}") from err
        except Exception as err:
            raise LLMProviderError(f"Unexpected error calling Groq: {err}") from err

        response_text = response.choices[0].message.content if response.choices else None
        if not response_text or not response_text.strip():
            raise LLMProviderError("Groq model returned an empty response.")
        return response_text
