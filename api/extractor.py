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

import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Sequence

import llm
from fields import (FIELD_TYPES, NUMERIC_BOUNDS, PROFILE_FIELDS, SLUG_FIELDS,
                    VOCABULARIES)
from jsonio import ExtractionError, parse_json_object, strip_fences  # noqa: F401  (re-exported)

PROMPT_PATH = Path(__file__).parent / "prompts" / "extractor_system.txt"

# Fields the interview will chase. Everything else is a bonus if volunteered.
REQUIRED_FIELDS: tuple[str, ...] = (
    "age",
    "area_type",
    "state",
    "sector",
    "has_existing_unit",
)

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def detect_language(text: str) -> str:
    """Devanagari anywhere in what the user wrote means answer in Hindi.

    Deliberately generous. Someone typing 'mujhe loan chahiye' in Latin script
    gets 'en', which is wrong for them but not harmful; someone typing one
    Devanagari word gets 'hi', which is right. We never guess the other way.
    """
    return "hi" if _DEVANAGARI.search(text) else "en"


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

    folded = unicodedata.normalize("NFKC", value).strip()

    allowed = VOCABULARIES.get(field)
    if allowed is not None:
        lowered = folded.lower()
        return lowered if lowered in allowed else None

    if field in SLUG_FIELDS:
        return re.sub(r"[\s-]+", "_", folded.lower())

    return folded


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


def user_text(conversation: Sequence[dict[str, str]]) -> str:
    return " ".join(t.get("text", "") for t in conversation if t.get("role") == "user")


def extract(
    conversation: Sequence[dict[str, str]],
    complete: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return {"profile": {...}, "missing": [...], "language": "hi"|"en"}.

    conversation is a list of {"role": "user"|"assistant", "text": str}.
    complete defaults to llm.complete; tests pass their own.

    On any model failure the profile comes back empty rather than wrong: an
    empty profile means the interview asks more questions, which is recoverable.
    """
    complete = complete or llm.complete
    language = detect_language(user_text(conversation))

    parsed = complete(load_system_prompt(), conversation) or {}
    profile = clean_profile(parsed.get("profile"))

    # Trust our own script detection over the model's self-report.
    model_language = parsed.get("language")
    if language == "en" and model_language in ("hi", "en"):
        language = model_language

    return {"profile": profile, "missing": missing_fields(profile), "language": language}
