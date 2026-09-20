"""Turn a conversation into a structured profile.

This is the first of exactly two places a model is used. It converts natural
language into fields. It does not decide eligibility, and nothing it returns
is trusted without checking: every value the model emits is re-validated here
against fields.py before it reaches the matcher.

If the model invents a field, misspells a value, or returns a number outside
plausible bounds, that value is dropped and the field is reported as missing.
Dropping is always safe - the interview will ask the person directly.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Sequence

from fields import FIELD_TYPES, NUMERIC_BOUNDS, PROFILE_FIELDS, VOCABULARIES

PROMPT_PATH = Path(__file__).parent / "prompts" / "extractor_system.txt"

# Fields the interview will chase. Everything else is a bonus if volunteered.
REQUIRED_FIELDS: tuple[str, ...] = (
    "age",
    "area_type",
    "state",
    "sector",
    "has_existing_unit",
)

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


class ExtractionError(RuntimeError):
    """The model returned something that is not a usable JSON object."""


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def detect_language(text: str) -> str:
    """Devanagari anywhere in what the user wrote means answer in Hindi.

    Deliberately generous. Someone typing 'mujhe loan chahiye' in Latin script
    gets 'en', which is wrong for them but not harmful; someone typing one
    Devanagari word gets 'hi', which is right. We never guess the other way.
    """
    return "hi" if _DEVANAGARI.search(text) else "en"


def strip_fences(raw: str) -> str:
    """Models wrap JSON in markdown fences no matter how firmly you ask them not to."""
    match = _FENCE.match(raw)
    if match:
        return match.group(1)
    return raw.strip()


def parse_json_object(raw: str) -> dict[str, Any]:
    text = strip_fences(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Last resort: the outermost {...} in the text.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ExtractionError(f"no JSON object in model output: {raw[:200]!r}")
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"model output is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ExtractionError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def clean_value(field: str, value: Any) -> Any | None:
    """Return the value if it is usable for this field, else None.

    None means 'we do not know', never 'false' and never 'zero'.
    """
    if value is None:
        return None

    # The model was told to omit unknowns. It sometimes says them out loud anyway.
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in {"unknown", "none", "null", "n/a", "na", "-"}:
            return None

    expected = FIELD_TYPES[field]

    if expected is bool:
        return value if isinstance(value, bool) else None

    if expected is int or expected == (int, float):
        # bool is an int in Python, and True must never become age 1.
        if isinstance(value, bool):
            return None
        if isinstance(value, str):
            try:
                value = float(value) if "." in value else int(value)
            except ValueError:
                return None
        if not isinstance(value, (int, float)):
            return None
        if expected is int:
            if isinstance(value, float) and not value.is_integer():
                return None
            value = int(value)
        lo, hi = NUMERIC_BOUNDS.get(field, (float("-inf"), float("inf")))
        return value if lo <= value <= hi else None

    if not isinstance(value, str):
        return None

    allowed = VOCABULARIES.get(field)
    if allowed is not None:
        folded = unicodedata.normalize("NFKC", value).strip().lower()
        return folded if folded in allowed else None

    return value


def clean_profile(raw_profile: Any) -> dict[str, Any]:
    """Keep only known fields holding usable values. Drop everything else silently."""
    if not isinstance(raw_profile, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for field in PROFILE_FIELDS:
        if field not in raw_profile:
            continue
        value = clean_value(field, raw_profile[field])
        if value is not None:
            cleaned[field] = value
    return cleaned


def missing_fields(profile: dict[str, Any]) -> list[str]:
    return [f for f in REQUIRED_FIELDS if f not in profile]


def build_messages(conversation: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    """Conversation turns into the Bedrock Converse message shape."""
    return [
        {"role": turn["role"], "content": [{"text": turn["text"]}]}
        for turn in conversation
        if turn.get("text")
    ]


def user_text(conversation: Sequence[dict[str, str]]) -> str:
    return " ".join(t.get("text", "") for t in conversation if t.get("role") == "user")


def call_model(client: Any, model_id: str, conversation: Sequence[dict[str, str]]) -> str:
    response = client.converse(
        modelId=model_id,
        system=[{"text": load_system_prompt()}],
        messages=build_messages(conversation),
        inferenceConfig={"maxTokens": 600, "temperature": 0},
    )
    return response["output"]["message"]["content"][0]["text"]


def extract(
    conversation: Sequence[dict[str, str]],
    client: Any,
    model_id: str,
) -> dict[str, Any]:
    """Return {"profile": {...}, "missing": [...], "language": "hi"|"en"}.

    conversation is a list of {"role": "user"|"assistant", "text": str}.
    On any model failure the profile comes back empty rather than wrong: an
    empty profile means the interview asks more questions, which is recoverable.
    """
    language = detect_language(user_text(conversation))

    try:
        parsed = parse_json_object(call_model(client, model_id, conversation))
    except ExtractionError:
        return {"profile": {}, "missing": list(REQUIRED_FIELDS), "language": language}

    profile = clean_profile(parsed.get("profile"))

    # Trust our own script detection over the model's self-report.
    model_language = parsed.get("language")
    if language == "en" and model_language in ("hi", "en"):
        language = model_language

    return {"profile": profile, "missing": missing_fields(profile), "language": language}
