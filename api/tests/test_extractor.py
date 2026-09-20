"""Extractor tests. No AWS calls - the Bedrock client is a stub."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import extractor
from fields import PROFILE_FIELDS
from jsonio import ExtractionError, parse_json_object

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schema" / "scheme.schema.json").read_text(encoding="utf-8")
)


class FakeLLM:
    """Stands in for llm.complete. Parses the raw text the way llm.py would."""

    def __init__(self, text: str):
        self.text = text
        self.calls: list[dict] = []

    def __call__(self, system, messages):
        self.calls.append({"system": system, "messages": list(messages)})
        try:
            return parse_json_object(self.text)
        except ExtractionError:
            return {}


def run(text: str, conversation=None):
    conversation = conversation or [{"role": "user", "text": "hello"}]
    return extractor.extract(conversation, FakeLLM(text))


# ---------------------------------------------------------------- the contract

def test_profile_fields_match_the_schema_enum():
    """If this fails, the extractor and the scheme corpus have drifted apart
    and schemes will silently stop matching."""
    schema_enum = SCHEMA["$defs"]["profile_field"]["enum"]
    assert sorted(PROFILE_FIELDS) == sorted(schema_enum)


def test_vocabularies_cover_only_known_fields():
    from fields import FIELD_TYPES, NUMERIC_BOUNDS, VOCABULARIES

    assert set(FIELD_TYPES) == set(PROFILE_FIELDS)
    assert set(VOCABULARIES) <= set(PROFILE_FIELDS)
    assert set(NUMERIC_BOUNDS) <= set(PROFILE_FIELDS)


# ------------------------------------------------------------- JSON robustness

def test_plain_json():
    out = run('{"profile": {"age": 32}, "language": "en"}')
    assert out["profile"] == {"age": 32}


def test_markdown_fenced_json():
    out = run('```json\n{"profile": {"age": 32}, "language": "en"}\n```')
    assert out["profile"] == {"age": 32}


def test_bare_fence_without_language_tag():
    out = run('```\n{"profile": {"age": 32}}\n```')
    assert out["profile"] == {"age": 32}


def test_json_with_chatter_around_it():
    out = run('Here is the profile:\n{"profile": {"age": 32}}\nHope that helps!')
    assert out["profile"] == {"age": 32}


def test_unparseable_output_yields_empty_profile_not_a_crash():
    out = run("I am sorry, I cannot help with that.")
    assert out["profile"] == {}
    assert set(out["missing"]) == set(extractor.REQUIRED_FIELDS)


def test_json_array_is_rejected():
    out = run('[{"age": 32}]')
    assert out["profile"] == {}


# ------------------------------------------------------------ never invent

def test_unknown_field_is_dropped():
    out = run('{"profile": {"age": 32, "favourite_colour": "blue"}}')
    assert out["profile"] == {"age": 32}


@pytest.mark.parametrize("junk", ["unknown", "", "  ", "N/A", "null", "-"])
def test_placeholder_strings_are_treated_as_missing(junk):
    out = run(json.dumps({"profile": {"state": junk, "age": 32}}))
    assert "state" not in out["profile"]
    assert "state" in out["missing"]


def test_explicit_null_is_missing_not_false():
    out = run('{"profile": {"has_existing_unit": null}}')
    assert "has_existing_unit" not in out["profile"]


def test_value_outside_vocabulary_is_dropped():
    out = run('{"profile": {"area_type": "semi-urban"}}')
    assert "area_type" not in out["profile"]


def test_vocabulary_values_are_case_normalised():
    out = run('{"profile": {"area_type": "RURAL", "caste_category": "  Obc "}}')
    assert out["profile"]["area_type"] == "rural"
    assert out["profile"]["caste_category"] == "obc"


@pytest.mark.parametrize("age", [7, 150, -3])
def test_implausible_age_is_dropped(age):
    out = run(json.dumps({"profile": {"age": age}}))
    assert "age" not in out["profile"]


def test_true_does_not_become_age_one():
    """bool is a subclass of int in Python. Without a guard, True becomes age 1."""
    out = run('{"profile": {"age": true}}')
    assert "age" not in out["profile"]


def test_number_as_string_is_accepted():
    out = run('{"profile": {"age": "32"}}')
    assert out["profile"]["age"] == 32


def test_non_bool_for_bool_field_is_dropped():
    out = run('{"profile": {"has_udyam_registration": "yes"}}')
    assert "has_udyam_registration" not in out["profile"]


def test_false_is_kept_and_is_not_confused_with_missing():
    out = run('{"profile": {"has_existing_unit": false}}')
    assert out["profile"]["has_existing_unit"] is False
    assert "has_existing_unit" not in out["missing"]


def test_zero_income_is_kept():
    out = run('{"profile": {"annual_income_inr": 0}}')
    assert out["profile"]["annual_income_inr"] == 0


# --------------------------------------------------------------- language

def test_devanagari_input_is_hindi():
    out = run('{"profile": {}, "language": "en"}',
              [{"role": "user", "text": "मैं दोना पत्तल बनाता हूँ"}])
    assert out["language"] == "hi"


def test_latin_input_is_english():
    out = run('{"profile": {}}', [{"role": "user", "text": "I make leaf plates"}])
    assert out["language"] == "en"


def test_one_devanagari_word_is_enough():
    out = run('{"profile": {}}', [{"role": "user", "text": "I make दोना at home"}])
    assert out["language"] == "hi"


def test_assistant_turns_do_not_decide_language():
    """The assistant asking a question in Hindi must not make an English user Hindi."""
    out = run('{"profile": {}}', [
        {"role": "assistant", "text": "आपकी उम्र क्या है?"},
        {"role": "user", "text": "I am 32"},
    ])
    assert out["language"] == "en"


# ------------------------------------------------------------ plumbing

def test_system_prompt_is_sent_and_lives_in_its_own_file():
    fake = FakeLLM('{"profile": {}}')
    extractor.extract([{"role": "user", "text": "hi"}], fake)
    assert fake.calls[0]["system"] == extractor.PROMPT_PATH.read_text(encoding="utf-8")
    assert extractor.PROMPT_PATH.suffix == ".txt"


def test_conversation_is_passed_through_in_order():
    fake = FakeLLM('{"profile": {}}')
    extractor.extract(
        [{"role": "user", "text": "one"},
         {"role": "assistant", "text": "two"},
         {"role": "user", "text": "three"}],
        fake,
    )
    sent = fake.calls[0]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert sent[0]["text"] == "one"


def test_missing_list_shrinks_as_fields_arrive():
    out = run(json.dumps({"profile": {
        "age": 32, "area_type": "rural", "state": "Madhya Pradesh",
        "sector": "leaf plates", "has_existing_unit": False,
    }}))
    assert out["missing"] == []
