"""
tests/unit/test_groq_provider.py

Unit tests for app.integrations.llm.groq_provider, focused on
_enforce_additional_properties_false() -- the fix for a real bug found live
against the Groq API: Groq's strict structured-output mode rejects a
schema unless EVERY object within it, at every nesting level, explicitly
sets additionalProperties: false, and Pydantic's model_json_schema() never
sets this anywhere by default. AnswerRubricScores (completely flat, no
nesting at all) failed at schema_path '$' -- the root object itself, not a
nested one -- so these tests cover both the flat and the genuinely nested
case, using a fake Groq client (never a real API call) to also confirm the
fix is actually wired into the outgoing request.
"""

from unittest.mock import MagicMock

from pydantic import BaseModel

from app.integrations.llm.groq_provider import GroqProvider, _enforce_additional_properties_false


class _FlatSchema(BaseModel):
    """Mirrors AnswerRubricScores's shape: no nested objects at all."""
    score: float


class _NestedItem(BaseModel):
    label: str
    value: bool


class _NestedSchema(BaseModel):
    """A schema with a real nested object via $defs -- mirrors SkillJudgmentBatch's shape."""
    items: list[_NestedItem]


# ---------------------------------------------------------------------------
# Test 1: A Flat Schema Gets additionalProperties: false at the Root
# ---------------------------------------------------------------------------
def test_enforce_additional_properties_false_on_flat_schema():
    """
    The bug as it actually manifested: a completely flat schema (no nested
    objects anywhere) was still rejected by Groq, because the ROOT object
    itself was missing additionalProperties: false -- Pydantic never sets
    this at any level by default, root included.
    """
    schema = _enforce_additional_properties_false(_FlatSchema.model_json_schema())

    assert schema["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Test 2: A Nested Schema Gets additionalProperties: false Recursively
# ---------------------------------------------------------------------------
def test_enforce_additional_properties_false_on_nested_schema():
    """The test the bug report specifically asked for: a schema with a nested object, checked recursively."""
    schema = _enforce_additional_properties_false(_NestedSchema.model_json_schema())

    assert schema["additionalProperties"] is False
    assert schema["$defs"]["_NestedItem"]["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Test 3: An Explicitly-Set additionalProperties Is Never Overwritten
# ---------------------------------------------------------------------------
def test_enforce_additional_properties_false_does_not_override_existing_value():
    """
    If a schema already states additionalProperties explicitly (however
    unusual for a Pydantic-generated one), the helper must not silently
    flip it -- only fill in what's missing.
    """
    schema = {"type": "object", "properties": {}, "additionalProperties": True}

    result = _enforce_additional_properties_false(schema)

    assert result["additionalProperties"] is True


# ---------------------------------------------------------------------------
# Test 4: The Fix Is Actually Wired Into the Outgoing Request
# ---------------------------------------------------------------------------
def test_generate_structured_sends_recursive_additional_properties_false():
    """
    Confirms the fix is actually used by generate_structured(), not just
    correct in isolation -- inspects the real request sent to a fake Groq
    client (never a real API call).
    """
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content='{"items": []}'))]

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    provider = GroqProvider(client=fake_client)
    provider.generate_structured(
        prompt="p",
        system_instruction="s",
        response_schema=_NestedSchema,
        temperature=0.0,
    )

    sent_schema = fake_client.chat.completions.create.call_args.kwargs["response_format"]["json_schema"]["schema"]
    assert sent_schema["additionalProperties"] is False
    assert sent_schema["$defs"]["_NestedItem"]["additionalProperties"] is False
