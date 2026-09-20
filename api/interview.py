"""Decide the single next question to ask.

Two rules shape this file.

One question at a time, never a form. Someone describing their work in a
second language, possibly on a borrowed phone, will not fill in eight fields.

Stop as soon as anything useful can be said. The moment one scheme matches
outright, the interview ends and the person gets an answer. Asking four more
questions to tighten a result they already have is how you lose someone.

No model runs here. Question order is computed from the scheme corpus by
matcher.fields_that_would_help, so the most discriminating question is asked
first. Add a scheme and the order changes on its own.
"""

from __future__ import annotations

from typing import Any, Sequence

from extractor import REQUIRED_FIELDS
from fields import (BOOLEAN_LABELS, CHOICE_LABELS, PROFILE_FIELDS, RANGES,
                    STATES, VOCABULARIES)
from matcher import fields_that_would_help, match

# After this many questions, answer with what is known. An interview that
# drags is worse than a slightly less precise answer.
MAX_QUESTIONS = 4

# Asked verbatim. Short sentences, common words, no officialese.
QUESTIONS: dict[str, dict[str, str]] = {
    "age": {
        "en": "How old are you?",
        "hi": "आपकी उम्र कितनी है?",
    },
    "area_type": {
        "en": "Do you live in a village or in a city?",
        "hi": "आप गाँव में रहते हैं या शहर में?",
    },
    "state": {
        "en": "Which state do you live in?",
        "hi": "आप किस राज्य में रहते हैं?",
    },
    "district": {
        "en": "Which district do you live in?",
        "hi": "आप किस जिले में रहते हैं?",
    },
    "sector": {
        "en": "What kind of work do you do?",
        "hi": "आप किस तरह का काम करते हैं?",
    },
    "has_existing_unit": {
        "en": "Do you already run a business or workshop?",
        "hi": "क्या आपका पहले से कोई काम या इकाई चल रही है?",
    },
    "has_udyam_registration": {
        "en": "Do you have a Udyam registration?",
        "hi": "क्या आपके पास उद्यम पंजीकरण है?",
    },
    "caste_category": {
        "en": "Which category do you belong to: general, OBC, SC or ST?",
        "hi": "आप किस श्रेणी में आते हैं: सामान्य, ओबीसी, एससी या एसटी?",
    },
    "gender": {
        "en": "Are you a woman, a man, or another gender?",
        "hi": "क्या आप महिला हैं, पुरुष हैं, या अन्य?",
    },
    "annual_income_inr": {
        "en": "Roughly how much do you earn in a year?",
        "hi": "आप साल में लगभग कितना कमा लेते हैं?",
    },
    "investment_planned_inr": {
        "en": "How much money do you plan to put into this work?",
        "hi": "आप इस काम में लगभग कितना पैसा लगाने की सोच रहे हैं?",
    },
}

# Fallback order when the corpus cannot discriminate, e.g. an empty profile
# where nothing is pending yet. Broadest first.
FALLBACK_ORDER: tuple[str, ...] = REQUIRED_FIELDS


def _askable(field: str) -> bool:
    return field in PROFILE_FIELDS and field in QUESTIONS


def should_stop(
    profile: dict[str, Any],
    schemes: Sequence[dict],
    asked: Sequence[str] = (),
    language: str = "en",
) -> bool:
    """True when the person should be given an answer instead of a question."""
    if len(asked) >= MAX_QUESTIONS:
        return True

    results = match(profile, schemes, language)

    # Something already qualifies outright. Say so now.
    if results["matched"]:
        return True

    # Nothing left that a question could resolve.
    if not results["likely"] and not results["matched"]:
        return True

    return not _candidates(profile, results, asked)


def _candidates(
    profile: dict[str, Any],
    results: dict[str, list[dict]],
    asked: Sequence[str],
) -> list[str]:
    """Fields worth asking about, most discriminating first."""
    ranked = [
        f for f in fields_that_would_help(results)
        if f not in profile and f not in asked and _askable(f)
    ]
    # Only fall back to generic questions when the corpus offers no specific
    # ones. Asking something that cannot change any verdict wastes a turn.
    if not ranked and not results.get("likely"):
        for field in FALLBACK_ORDER:
            if field not in profile and field not in asked and _askable(field):
                ranked.append(field)
    return ranked


def options_for(field: str, language: str) -> tuple[str, list[dict]]:
    """What the person taps instead of typing.

    Returns (input_type, options). Typing is the fallback, not the default:
    a tap cannot be misspelled, cannot be misread, and does not need a
    keyboard someone may not have in their own script.
    """
    if field in RANGES:
        return "range", [
            {
                "value": {"min": b["min"], "max": b["max"]},
                "label": b[f"label_{language}"] if f"label_{language}" in b else b["label_en"],
            }
            for b in RANGES[field]
        ]

    if field in BOOLEAN_LABELS:
        return "choice", [
            {"value": value, "label": labels.get(language, labels["en"])}
            for value, labels in BOOLEAN_LABELS[field].items()
        ]

    if field == "state":
        return "select", [
            {"value": slug, "label": hi if language == "hi" else en}
            for slug, en, hi in STATES
        ]

    if field in CHOICE_LABELS:
        labels = CHOICE_LABELS[field]
        return "choice", [
            {"value": value, "label": labels[value].get(language, labels[value]["en"])}
            for value in VOCABULARIES.get(field, tuple(labels))
            if value in labels
        ]

    return "text", []


def next_question(
    profile: dict[str, Any],
    schemes: Sequence[dict],
    asked: Sequence[str] = (),
    language: str = "en",
) -> dict[str, Any] | None:
    """The one question to ask next, or None when it is time to answer.

    Returns {"field": ..., "text": ..., "language": ..., "asked_count": n}.
    """
    if should_stop(profile, schemes, asked, language):
        return None

    results = match(profile, schemes, language)
    candidates = _candidates(profile, results, asked)
    if not candidates:
        return None

    field = candidates[0]
    input_type, options = options_for(field, language)
    return {
        "field": field,
        "text": QUESTIONS[field].get(language, QUESTIONS[field]["en"]),
        "input_type": input_type,
        "options": options,
        "language": language,
        "asked_count": len(asked) + 1,
        "unblocks": sum(
            1 for r in results["likely"]
            for p in r["pending"] if p.get("field") == field
        ),
    }
