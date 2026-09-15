"""
tests/unit/test_chained_llm_provider.py

Unit tests for app.integrations.llm.fallback_provider.ChainedLLMProvider,
using fake LLMProvider implementations (never a real Gemini/xAI/Groq call)
so the routing logic itself is proven independent of whether any real
service is reachable.

Renamed from test_fallback_provider.py (FallbackLLMProvider -> the more
general ChainedLLMProvider) when a third provider (Groq) was added and a
single shared primary/fallback pair could no longer express the chain.
Tests 1-5 are the original two-provider tests translated to the list-based
constructor; tests 6-7 are new, proving the actual 3+-link generalization.
"""

import pytest

from app.integrations.llm.base import LLMProvider, LLMProviderError
from app.integrations.llm.fallback_provider import ChainedLLMProvider


class _FakeProvider(LLMProvider):
    """Records whether it was called; either returns a fixed string or raises a given exception."""

    def __init__(self, *, result: str = "", raises: Exception = None):
        self.result = result
        self.raises = raises
        self.called = False

    def generate_structured(self, *, prompt, system_instruction, response_schema, temperature=None):
        self.called = True
        if self.raises is not None:
            raise self.raises
        return self.result


class _TransientError(Exception):
    """Stand-in for a real provider's transient/5xx-class exception."""


class _NonTransientError(Exception):
    """Stand-in for a real provider's non-transient/4xx-class exception."""


def _call_kwargs():
    return dict(prompt="p", system_instruction="s", response_schema=dict, temperature=0.1)


def _is_transient(err: LLMProviderError) -> bool:
    return isinstance(err.__cause__, _TransientError)


# ---------------------------------------------------------------------------
# Test 1: First Link Succeeds -- No Other Link Ever Called
# ---------------------------------------------------------------------------
def test_first_link_success_never_calls_later_links():
    first = _FakeProvider(result='{"ok": true}')
    second = _FakeProvider(result='{"should": "not see this"}')
    provider = ChainedLLMProvider([(first, _is_transient), (second, _is_transient)])

    result = provider.generate_structured(**_call_kwargs())

    assert result == '{"ok": true}'
    assert first.called is True
    assert second.called is False


# ---------------------------------------------------------------------------
# Test 2: Transient First-Link Failure Falls Back, and the Second Link's Result Wins
# ---------------------------------------------------------------------------
def test_transient_failure_falls_back_to_next_link():
    first_error = LLMProviderError("first link down")
    first_error.__cause__ = _TransientError("503-equivalent")
    first = _FakeProvider(raises=first_error)
    second = _FakeProvider(result='{"from": "second link"}')

    provider = ChainedLLMProvider([(first, _is_transient), (second, _is_transient)])

    result = provider.generate_structured(**_call_kwargs())

    assert result == '{"from": "second link"}'
    assert first.called is True
    assert second.called is True


# ---------------------------------------------------------------------------
# Test 3: Non-Transient Failure Propagates -- No Other Link Ever Called
# ---------------------------------------------------------------------------
def test_non_transient_failure_never_falls_back():
    """
    A non-transient failure (e.g. a validation-shaped or client-error-shaped
    problem) must propagate directly, not silently retry against a
    different model with different behavior.
    """
    first_error = LLMProviderError("bad request")
    first_error.__cause__ = _NonTransientError("400-equivalent")
    first = _FakeProvider(raises=first_error)
    second = _FakeProvider(result='{"should": "not be reached"}')

    provider = ChainedLLMProvider([(first, _is_transient), (second, _is_transient)])

    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(**_call_kwargs())

    assert exc_info.value is first_error
    assert first.called is True
    assert second.called is False


# ---------------------------------------------------------------------------
# Test 4: Every Link Fails Transiently -- the Last Link's Error Propagates
# ---------------------------------------------------------------------------
def test_every_link_failing_propagates_last_links_error():
    first_error = LLMProviderError("first link down")
    first_error.__cause__ = _TransientError("503-equivalent")
    second_error = LLMProviderError("second link also down")
    second_error.__cause__ = _TransientError("503-equivalent")

    first = _FakeProvider(raises=first_error)
    second = _FakeProvider(raises=second_error)

    provider = ChainedLLMProvider([(first, _is_transient), (second, _is_transient)])

    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(**_call_kwargs())

    assert exc_info.value is second_error
    assert first.called is True
    assert second.called is True


# ---------------------------------------------------------------------------
# Test 5: Call Arguments Are Passed Through Unchanged to Every Link
# ---------------------------------------------------------------------------
def test_call_arguments_forwarded_unchanged_to_next_link():
    """
    The exact same prompt/system_instruction/response_schema/temperature
    used against the first link must be replayed against the next -- not a
    reconstructed or partial call.
    """
    received = {}

    class _RecordingProvider(LLMProvider):
        def generate_structured(self, *, prompt, system_instruction, response_schema, temperature=None):
            received["prompt"] = prompt
            received["system_instruction"] = system_instruction
            received["response_schema"] = response_schema
            received["temperature"] = temperature
            return "recorded"

    first_error = LLMProviderError("first link down")
    first_error.__cause__ = _TransientError("503-equivalent")
    first = _FakeProvider(raises=first_error)
    second = _RecordingProvider()

    provider = ChainedLLMProvider([(first, _is_transient), (second, _is_transient)])

    kwargs = _call_kwargs()
    result = provider.generate_structured(**kwargs)

    assert result == "recorded"
    assert received == kwargs


# ---------------------------------------------------------------------------
# Test 6: Three-Link Chain -- Falls Through Two Transient Failures to the Third
# ---------------------------------------------------------------------------
def test_three_link_chain_falls_through_to_third_link():
    """Proves the actual N>2 generalization, not just the 2-link case renamed."""
    first_error = LLMProviderError("Gemini-equivalent down")
    first_error.__cause__ = _TransientError("503-equivalent")
    second_error = LLMProviderError("xAI-equivalent down")
    second_error.__cause__ = _TransientError("UNAVAILABLE-equivalent")

    first = _FakeProvider(raises=first_error)
    second = _FakeProvider(raises=second_error)
    third = _FakeProvider(result='{"from": "third link"}')

    provider = ChainedLLMProvider([(first, _is_transient), (second, _is_transient), (third, _is_transient)])

    result = provider.generate_structured(**_call_kwargs())

    assert result == '{"from": "third link"}'
    assert first.called is True
    assert second.called is True
    assert third.called is True


# ---------------------------------------------------------------------------
# Test 7: Three-Link Chain -- a Non-Transient Middle-Link Failure Stops Immediately
# ---------------------------------------------------------------------------
def test_three_link_chain_stops_at_non_transient_middle_link():
    """A non-transient failure on a non-last link must still stop the whole chain, not just skip to the next."""
    first_error = LLMProviderError("Gemini-equivalent down")
    first_error.__cause__ = _TransientError("503-equivalent")
    second_error = LLMProviderError("xAI-equivalent bad request")
    second_error.__cause__ = _NonTransientError("400-equivalent")

    first = _FakeProvider(raises=first_error)
    second = _FakeProvider(raises=second_error)
    third = _FakeProvider(result='{"should": "not be reached"}')

    provider = ChainedLLMProvider([(first, _is_transient), (second, _is_transient), (third, _is_transient)])

    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(**_call_kwargs())

    assert exc_info.value is second_error
    assert first.called is True
    assert second.called is True
    assert third.called is False


# ---------------------------------------------------------------------------
# Test 8: A Single-Link List Is Rejected
# ---------------------------------------------------------------------------
def test_single_link_raises_value_error():
    """ChainedLLMProvider only makes sense with at least 2 links -- a single link has no fallback behavior at all."""
    with pytest.raises(ValueError):
        ChainedLLMProvider([(_FakeProvider(result="x"), _is_transient)])
