"""
app/integrations/llm/factory.py

Single place that decides what "the default LLM provider" means for every
parser/service in this codebase, so the provider-chain wiring lives in
exactly one location instead of being duplicated across JDParser,
CVParser, and evaluate_answer()'s separate default-construction call sites.

Chain order: Gemini (primary, proven against real JD/CV/semantic-matching
data) -> xAI (second) -> Groq/openai/gpt-oss-120b (third, genuinely free
right now, but unvalidated against our real schemas -- deliberately never
primary). Gemini is always link 0 unconditionally; xAI/Groq are appended
only when their API keys are actually set, so the chain length -- and
therefore whether ChainedLLMProvider even needs to exist -- depends purely
on what's configured in .env, not on a code change.

Each link's transience predicate is specific to that provider's real error
shape, confirmed empirically for all three (see gemini_provider.py/
xai_provider.py/groq_provider.py's docstrings): Gemini raises
google.genai.errors.ServerError, xAI raises grpc.RpcError with
grpc.StatusCode.UNAVAILABLE, Groq raises groq.InternalServerError. A single
shared predicate could not correctly classify all three -- see
fallback_provider.py's docstring for why ChainedLLMProvider takes a
predicate per link rather than one shared one.

get_default_provider() returns a plain GeminiProvider() when neither
XAI_API_KEY nor GROQ_API_KEY is set -- today's original, unchanged
behavior -- so every additional link is strictly opt-in: adding an env var
is what extends the chain, not a code change.
"""
import os
import threading
from typing import Optional

import grpc
from google.genai.errors import ServerError
from groq import InternalServerError as GroqInternalServerError

from app.integrations.llm.base import LLMProvider, LLMProviderError
from app.integrations.llm.fallback_provider import ChainedLLMProvider
from app.integrations.llm.gemini_provider import GeminiProvider
from app.integrations.llm.groq_provider import GroqProvider
from app.integrations.llm.xai_provider import XAIProvider

_provider_lock = threading.Lock()
_cached_provider: Optional[LLMProvider] = None
_cached_key: Optional[tuple] = None


def _is_gemini_transient_error(err: LLMProviderError) -> bool:
    """True only for a Gemini ServerError (5xx) -- never a ClientError (4xx) or anything else."""
    return isinstance(err.__cause__, ServerError)


def _is_xai_transient_error(err: LLMProviderError) -> bool:
    """True only for a grpc.RpcError with status UNAVAILABLE -- e.g. a bad API key (INVALID_ARGUMENT) is not transient."""
    cause = err.__cause__
    return isinstance(cause, grpc.RpcError) and cause.code() == grpc.StatusCode.UNAVAILABLE


def _is_groq_transient_error(err: LLMProviderError) -> bool:
    """True only for a Groq InternalServerError (5xx) -- never RateLimitError/AuthenticationError/etc."""
    return isinstance(err.__cause__, GroqInternalServerError)


def _provider_cache_key() -> tuple:
    return (
        os.getenv("GEMINI_API_KEY"),
        os.getenv("GEMINI_MODEL"),
        bool(os.getenv("XAI_API_KEY")),
        bool(os.getenv("GROQ_API_KEY")),
    )


def _build_default_provider() -> LLMProvider:
    links = [(GeminiProvider(), _is_gemini_transient_error)]
    if os.getenv("XAI_API_KEY"):
        links.append((XAIProvider(), _is_xai_transient_error))
    if os.getenv("GROQ_API_KEY"):
        links.append((GroqProvider(), _is_groq_transient_error))

    if len(links) == 1:
        return links[0][0]
    return ChainedLLMProvider(links)


def reset_default_provider_cache_for_tests() -> None:
    global _cached_provider, _cached_key
    with _provider_lock:
        _cached_provider = None
        _cached_key = None


def get_default_provider() -> LLMProvider:
    """Return the process-cached default LLM provider.

    Answer evaluation used to construct a new GeminiProvider (and later a new
    genai.Client) on every candidate turn. Reusing the same provider keeps the
    HTTP client/session warm without sharing it across asyncio event loops —
    this client is synchronous and used from worker threads.
    """
    global _cached_provider, _cached_key
    key = _provider_cache_key()
    with _provider_lock:
        if _cached_provider is not None and _cached_key == key:
            return _cached_provider
        provider = _build_default_provider()
        _cached_provider = provider
        _cached_key = key
        return provider
