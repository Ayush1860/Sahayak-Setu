"""Who qualifies for what. Decided here, in plain Python, and nowhere else.

READ THIS FILE IF YOU WANT TO KNOW HOW ELIGIBILITY IS DECIDED.

There is no model in this file. There is no network call in this file. There
is no prompt in this file. The only imports are from the Python standard
library and from fields.py, which is a list of strings. Nothing here can
reach Bedrock even by accident, and test_matcher.py asserts that by reading
this module's own import statements.

A model runs before this file, turning what a person said into a dict. A
model runs after it, turning this file's output into readable Hindi. Between
those two points, a scheme qualifies or does not qualify because of the code
below and the eligibility blocks in /schemes/*.json.

HOW IT WORKS

Every criterion evaluates to one of three outcomes:

    PASS     the profile satisfies it
    FAIL     the profile violates it
    UNKNOWN  the profile does not say

UNKNOWN is the important one. It is not a pass and it is not a fail. A field
nobody has been asked about yet cannot rule someone in or out, so it becomes
a question to answer rather than a verdict.

A scheme's verdict follows from its criteria with no judgement calls:

    any FAIL          -> excluded, naming every criterion that failed
    else any UNKNOWN  -> likely, listing what still has to be confirmed
    else              -> matched

"matched" still means "likely eligible, confirm at the office". This module
never reports that anyone is entitled to anything. Only an officer with the
documents in hand can say that, and the wording of every verdict says so.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, Sequence

from fields import PROFILE_FIELDS


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class Verdict(str, Enum):
    MATCHED = "matched"
    LIKELY = "likely"
    EXCLUDED = "excluded"


# The wording used wherever a verdict is spoken aloud. Deliberately not
# "eligible" - see the module docstring.
VERDICT_TEXT = {
    Verdict.MATCHED: "likely eligible, confirm at the office",
    Verdict.LIKELY: "possibly eligible, some things still to confirm",
    Verdict.EXCLUDED: "does not meet a requirement",
}


# --------------------------------------------------------------------------
# The five tests. Each takes a criterion and the person's value for its field,
# and returns one outcome. They are pure functions of their arguments.
# --------------------------------------------------------------------------

def _test_range(criterion: dict, value: Any) -> Outcome:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return Outcome.UNKNOWN
    low = criterion.get("min")
    high = criterion.get("max")
    if low is not None and value < low:
        return Outcome.FAIL
    if high is not None and value > high:
        return Outcome.FAIL
    return Outcome.PASS


def _test_one_of(criterion: dict, value: Any) -> Outcome:
    return Outcome.PASS if value in criterion.get("values", []) else Outcome.FAIL


def _test_none_of(criterion: dict, value: Any) -> Outcome:
    return Outcome.FAIL if value in criterion.get("values", []) else Outcome.PASS


def _test_boolean(criterion: dict, value: Any) -> Outcome:
    if not isinstance(value, bool):
        return Outcome.UNKNOWN
    return Outcome.PASS if value is criterion.get("expected") else Outcome.FAIL


def _test_manual(criterion: dict, value: Any) -> Outcome:
    """A condition code cannot decide. Always a question, never a verdict."""
    return Outcome.UNKNOWN


TESTS = {
    "range": _test_range,
    "one_of": _test_one_of,
    "none_of": _test_none_of,
    "boolean": _test_boolean,
    "manual": _test_manual,
}


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

def evaluate_criterion(criterion: dict, profile: dict[str, Any]) -> Outcome:
    """One criterion against one profile.

    A field the profile does not carry is UNKNOWN before any test runs. This
    single line is what stops a half-finished interview from excluding anyone.
    """
    test = criterion.get("test")
    if test not in TESTS:
        # An unrecognised test is a bug in the scheme file, not a reason to
        # rule someone out. Fail towards asking a human.
        return Outcome.UNKNOWN

    if test != "manual":
        field = criterion.get("field")
        if field not in PROFILE_FIELDS:
            return Outcome.UNKNOWN
        if field not in profile:
            return Outcome.UNKNOWN
        return TESTS[test](criterion, profile[field])

    return TESTS[test](criterion, None)


def _cite(criterion: dict) -> dict[str, Any]:
    """The shape every reason takes. Always carries its source page."""
    return {
        "criterion_id": criterion.get("criterion_id"),
        "field": criterion.get("field"),
        "label_en": criterion.get("label_en"),
        "label_hi": criterion.get("label_hi"),
        "source_page": criterion.get("source_page"),
    }


def _fail_reason(criterion: dict, language: str) -> str:
    override = criterion.get(f"fail_reason_{language}")
    if override:
        return override
    label = criterion.get(f"label_{language}") or criterion.get("label_en") or ""
    if language == "hi":
        return f"यह शर्त पूरी नहीं होती: {label}"
    return f"This requirement is not met: {label}"


def evaluate_scheme(scheme: dict, profile: dict[str, Any], language: str = "en") -> dict[str, Any]:
    """One scheme against one profile. Returns the verdict and why."""
    criteria = (scheme.get("eligibility") or {}).get("criteria") or []

    met: list[dict] = []
    pending: list[dict] = []
    failed: list[dict] = []

    for criterion in criteria:
        outcome = evaluate_criterion(criterion, profile)
        if outcome is Outcome.PASS:
            met.append(_cite(criterion))
        elif outcome is Outcome.FAIL:
            entry = _cite(criterion)
            entry["reason"] = _fail_reason(criterion, language)
            failed.append(entry)
        else:
            pending.append(_cite(criterion))

    if failed:
        verdict = Verdict.EXCLUDED
    elif pending:
        verdict = Verdict.LIKELY
    else:
        verdict = Verdict.MATCHED

    return {
        "scheme_id": scheme.get("scheme_id"),
        "name_en": scheme.get("name_en"),
        "name_hi": scheme.get("name_hi"),
        "verdict": verdict.value,
        "verdict_text": VERDICT_TEXT[verdict],
        "reasons_met": met,
        "pending": pending,
        "failed": failed,
        "reason": _summarise(verdict, met, pending, failed, language),
    }


def _summarise(
    verdict: Verdict,
    met: Sequence[dict],
    pending: Sequence[dict],
    failed: Sequence[dict],
    language: str,
) -> str:
    """One human-readable sentence naming the criteria that decided this."""
    key = f"label_{language}"

    def labels(items: Sequence[dict]) -> str:
        return "; ".join(i.get(key) or i.get("label_en") or "" for i in items)

    if verdict is Verdict.EXCLUDED:
        return failed[0]["reason"]

    if verdict is Verdict.MATCHED:
        if language == "hi":
            return f"आप ये शर्तें पूरी करते हैं: {labels(met)}। कार्यालय में पुष्टि करें।"
        return f"You meet these requirements: {labels(met)}. Confirm at the office."

    if language == "hi":
        head = f"आप ये शर्तें पूरी करते हैं: {labels(met)}। " if met else ""
        return f"{head}अभी यह जानना बाकी है: {labels(pending)}।"
    head = f"You meet these requirements: {labels(met)}. " if met else ""
    return f"{head}Still to confirm: {labels(pending)}."


def match(
    profile: dict[str, Any],
    schemes: Iterable[dict],
    language: str = "en",
    include_placeholders: bool = False,
) -> dict[str, list[dict]]:
    """Every scheme against one profile, sorted into three buckets.

    Placeholder scheme files are held back by default and reported separately,
    so unverified content cannot reach a user through an oversight.
    """
    results: dict[str, list[dict]] = {"matched": [], "likely": [], "excluded": [], "skipped": []}

    for scheme in schemes:
        if scheme.get("PLACEHOLDER") and not include_placeholders:
            results["skipped"].append({
                "scheme_id": scheme.get("scheme_id"),
                "reason": "PLACEHOLDER scheme, not hand verified, withheld from results",
            })
            continue
        result = evaluate_scheme(scheme, profile, language)
        results[result["verdict"]].append(result)

    # Most-confirmed first within each bucket. Stable, so ties keep corpus order.
    for bucket in ("matched", "likely", "excluded"):
        results[bucket].sort(key=lambda r: len(r["reasons_met"]), reverse=True)

    return results


def fields_that_would_help(results: dict[str, list[dict]]) -> list[str]:
    """Profile fields that are currently blocking the most schemes.

    The interview uses this to pick its next question: asking about the field
    that appears in the most pending lists resolves the most schemes at once.
    """
    counts: dict[str, int] = {}
    for result in results.get("likely", []):
        for item in result["pending"]:
            field = item.get("field")
            if field in PROFILE_FIELDS:
                counts[field] = counts.get(field, 0) + 1
    return sorted(counts, key=lambda f: (-counts[f], f))
