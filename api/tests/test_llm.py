"""Provider interface tests. No provider is ever contacted."""

from __future__ import annotations

import pytest

import llm
from jsonio import ExtractionError, parse_json_object, strip_fences


def test_both_providers_are_registered():
    assert set(llm.PROVIDERS) == {"groq", "bedrock"}


def test_unknown_provider_is_a_loud_error(monkeypatch):
    """A typo in LLM_PROVIDER must fail visibly, not silently return nothing."""
    monkeypatch.setattr(llm, "PROVIDER", "gorq")
    with pytest.raises(llm.LLMError):
        llm.complete("s", [{"role": "user", "text": "x"}])


def test_provider_failure_returns_empty_not_a_guess(monkeypatch):
    def boom(system, messages):
        raise RuntimeError("provider is down")

    monkeypatch.setitem(llm.PROVIDERS, "groq", boom)
    monkeypatch.setattr(llm, "PROVIDER", "groq")
    assert llm.complete("s", [{"role": "user", "text": "x"}]) == {}


def test_unparseable_output_returns_empty(monkeypatch):
    def garbage(system, messages):
        raise ExtractionError("not json")

    monkeypatch.setitem(llm.PROVIDERS, "groq", garbage)
    monkeypatch.setattr(llm, "PROVIDER", "groq")
    assert llm.complete("s", [{"role": "user", "text": "x"}]) == {}


def test_switching_provider_changes_nothing_else(monkeypatch):
    """The swap is one variable. This is the claim the architecture rests on."""
    seen = []

    def groq(system, messages):
        seen.append("groq")
        return {"ok": True}

    def bedrock(system, messages):
        seen.append("bedrock")
        return {"ok": True}

    monkeypatch.setitem(llm.PROVIDERS, "groq", groq)
    monkeypatch.setitem(llm.PROVIDERS, "bedrock", bedrock)

    monkeypatch.setattr(llm, "PROVIDER", "groq")
    assert llm.complete("s", []) == {"ok": True}
    monkeypatch.setattr(llm, "PROVIDER", "bedrock")
    assert llm.complete("s", []) == {"ok": True}
    assert seen == ["groq", "bedrock"]


def test_describe_reports_what_is_configured(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "groq")
    monkeypatch.setattr(llm, "GROQ_MODEL", "some-model")
    assert llm.describe() == {"provider": "groq", "model": "some-model"}


def test_no_api_key_appears_in_describe(monkeypatch):
    """describe() is returned to the browser. It must never leak the key."""
    monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_secret_value")
    assert "gsk_secret_value" not in str(llm.describe())


# ------------------------------------------------------- JSON handling

@pytest.mark.parametrize("raw,expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('```\n{"a": 1}\n```', {"a": 1}),
    ('Sure! {"a": 1} hope that helps', {"a": 1}),
])
def test_json_survives_the_usual_model_wrapping(raw, expected):
    assert parse_json_object(raw) == expected


@pytest.mark.parametrize("raw", ["not json at all", "[1, 2, 3]", ""])
def test_unusable_output_raises(raw):
    with pytest.raises(ExtractionError):
        parse_json_object(raw)


def test_strip_fences_leaves_plain_text_alone():
    assert strip_fences('  {"a": 1}  ') == '{"a": 1}'
