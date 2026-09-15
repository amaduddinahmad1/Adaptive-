"""
app/integrations/llm/fallback_provider.py

ChainedLLMProvider tries an ordered list of providers, moving to the next
only when the current one fails with an error its own paired `is_transient`
predicate classifies as transient -- never for anything else, so a bad
prompt or a genuine validation problem doesn't get silently retried against
a different model with different behavior.

Originally a two-provider FallbackLLMProvider (primary/fallback/one shared
predicate); generalized to an ordered list of (provider, is_transient)
pairs once a third provider (Groq) was added. A single shared predicate
cannot correctly classify all three real providers' errors: Gemini raises
google.genai.errors.ServerError, xAI raises grpc.RpcError with a
grpc.StatusCode, and Groq raises groq.InternalServerError -- three
structurally different exception shapes, confirmed empirically for each
(see gemini_provider.py/xai_provider.py/groq_provider.py). Each link
therefore supplies its own predicate rather than sharing one. This is a
strict generalization: a 2-link chain behaves identically to the original
two-provider design.

A non-transient failure on any link -- including a non-last one -- stops
the whole chain immediately and propagates, rather than cascading through
every remaining provider hoping one behaves differently.

Deliberately not tied to any specific providers: which errors count as
"transient" is supplied by the caller per link, since that classification
is provider-specific. See factory.py for how this is wired up for the
actual Gemini -> xAI -> Groq chain used in this codebase.

pydantic.ValidationError is never seen here at all -- it's raised one layer
above generate_structured(), inside JDParser.parse()/CVParser.parse()/
day5_answer_evaluation._request_scores() themselves, after the provider
call has already returned text successfully. Every LLMProvider in this
codebase guarantees that anything escaping generate_structured() is an
LLMProviderError, so "don't fall back on validation errors" is satisfied by
that existing call layering, not something this class needs to special-case.
"""
from typing import Any, Callable, List, Optional, Tuple

from app.integrations.llm.base import LLMProvider, LLMProviderError


class ChainedLLMProvider(LLMProvider):
    """Tries each (provider, is_transient) link in order; stops at the first success or non-transient failure."""

    def __init__(self, links: List[Tuple[LLMProvider, Callable[[LLMProviderError], bool]]]):
        if len(links) < 2:
            raise ValueError("ChainedLLMProvider needs at least 2 links to have any fallback behavior.")
        self.links = links

    def generate_structured(
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: Any,
        temperature: Optional[float] = None,
    ) -> str:
        last_link_index = len(self.links) - 1
        for index, (provider, is_transient) in enumerate(self.links):
            try:
                return provider.generate_structured(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    response_schema=response_schema,
                    temperature=temperature,
                )
            except LLMProviderError as err:
                if index == last_link_index or not is_transient(err):
                    raise
