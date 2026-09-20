"""Which rate modifiers apply to this person.

Selection only. There is no arithmetic in this file, and there must never be.

A scheme states a base rate and a set of modifiers, each transcribed verbatim
from the source. This module decides which of those strings apply to a
profile. It does not add them together, and it does not produce a combined
figure, because the source does not state one.

That is not caution for its own sake. "40% of eligible investment" paid in
four annual instalments, plus "an additional 2.5% per year for four years",
does not obviously total 42.5% and may well total 50%. The page does not say.
Anything this system displayed would be an interpretation, and an
interpretation about how much money someone receives is exactly the kind of
claim that must come from an officer, not from software.

So the card shows the base rate and the applicable modifiers as separate
lines, each in the source's own words, each with its page number.

Three outcomes, mirroring matcher.py:

    applies      the profile satisfies the selector
    possible     the profile does not say; shown as "may also apply"
    not_applicable  the profile rules it out; not shown at all
"""

from __future__ import annotations

from typing import Any, Sequence

from matcher import Outcome, evaluate_criterion


def _evaluate(when: dict | None, profile: dict[str, Any]) -> Outcome:
    """Evaluate a selector against a profile.

    A modifier with no selector is informational: the source states it, but
    nothing in the profile can confirm it. Export share is the example here;
    we never ask a leaf-plate maker what proportion of sales they export.
    """
    if not isinstance(when, dict):
        return Outcome.UNKNOWN

    kind = when.get("type")

    if kind == "always":
        return Outcome.PASS

    conditions = when.get("conditions") or []
    if kind not in ("all", "any") or not conditions:
        return Outcome.UNKNOWN

    outcomes = [evaluate_criterion(c, profile) for c in conditions]

    if kind == "all":
        if any(o is Outcome.FAIL for o in outcomes):
            return Outcome.FAIL
        if all(o is Outcome.PASS for o in outcomes):
            return Outcome.PASS
        return Outcome.UNKNOWN

    if any(o is Outcome.PASS for o in outcomes):
        return Outcome.PASS
    if all(o is Outcome.FAIL for o in outcomes):
        return Outcome.FAIL
    return Outcome.UNKNOWN


def select(
    scheme: dict,
    profile: dict[str, Any],
    language: str = "en",
) -> dict[str, list[dict]]:
    """Return the modifier strings that apply, and those that might.

    Every string returned is copied verbatim from the scheme file. Nothing
    here is generated, combined or rounded.
    """
    applies: list[dict] = []
    possible: list[dict] = []

    modifiers = scheme.get("rate_modifiers") or []
    superseded = {
        m.get("supersedes") for m in modifiers
        if m.get("supersedes") and _evaluate(m.get("when"), profile) is Outcome.PASS
    }

    for modifier in modifiers:
        modifier_id = modifier.get("modifier_id")
        if modifier_id in superseded:
            # A more specific modifier applies instead. The scheme file says
            # which supersedes which; this module never decides that.
            continue

        outcome = _evaluate(modifier.get("when"), profile)
        if outcome is Outcome.FAIL:
            continue

        entry = {
            "modifier_id": modifier_id,
            "rate": modifier.get(f"rate_{language}") or modifier.get("rate_en"),
            "condition": modifier.get("applies_when"),
            "source_page": modifier.get("source_page"),
        }
        (applies if outcome is Outcome.PASS else possible).append(entry)

    return {"applies": applies, "possible": possible}


def as_strings(selected: Sequence[dict]) -> list[str]:
    return [s["rate"] for s in selected if s.get("rate")]
