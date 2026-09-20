"""Task C: an unread clause must become a question, never a silent pass.

clause_7_6_exclusions in the MP MSME scheme is test: "manual" because the
exclusions at 7.6(ii)(iii)(iv) have not been read from the source. The
honest behaviour is:

    it evaluates UNKNOWN
    the scheme is still offered, as "likely", not excluded
    the person is told to ask about it at the office

The failure this guards against is the quiet one: a criterion nobody can
evaluate being treated as satisfied, so the card says "you qualify" when the
truth is "we did not read that clause".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import explainer
import validator
from matcher import Outcome, Verdict, evaluate_criterion, evaluate_scheme, match

CORPUS = Path(__file__).resolve().parents[2] / "schemes"
REAL = json.loads((CORPUS / "mp_msme_industrial_development_subsidy.json").read_text(encoding="utf-8"))

EXCLUSIONS = next(
    c for c in REAL["eligibility"]["criteria"] if c["criterion_id"] == "clause_7_6_exclusions"
)

# The demo user: leaf plates in a village in MP, no existing unit.
DEMO_PROFILE = {
    "has_existing_unit": False,
    "sector": "manufacturing",
    "state": "madhya_pradesh",
    "area_type": "rural",
    "age": 32,
}


def test_the_criterion_is_still_manual():
    """If someone reads 7.6 and structures it, this test should be deleted
    deliberately, not discovered as a surprise."""
    assert EXCLUSIONS["test"] == "manual"
    assert "field" not in EXCLUSIONS


def test_it_evaluates_unknown_whatever_the_profile_says():
    assert evaluate_criterion(EXCLUSIONS, {}) is Outcome.UNKNOWN
    assert evaluate_criterion(EXCLUSIONS, DEMO_PROFILE) is Outcome.UNKNOWN


def test_it_never_excludes_the_scheme():
    result = evaluate_scheme(REAL, DEMO_PROFILE)
    assert result["verdict"] != Verdict.EXCLUDED.value
    assert EXCLUSIONS["criterion_id"] not in [f["criterion_id"] for f in result["failed"]]


def test_a_fully_known_profile_is_still_only_likely():
    """Everything else passes. The unread clause alone keeps it out of
    'matched', which is the point."""
    full = dict(DEMO_PROFILE, investment_planned_inr=500000)
    result = evaluate_scheme(REAL, full)
    assert result["verdict"] == Verdict.LIKELY.value
    assert [p["criterion_id"] for p in result["pending"]] == ["clause_7_6_exclusions"]


def test_it_is_never_counted_as_a_reason_the_person_qualifies():
    result = evaluate_scheme(REAL, DEMO_PROFILE)
    assert EXCLUSIONS["criterion_id"] not in [m["criterion_id"] for m in result["reasons_met"]]


def test_the_scheme_is_offered_to_the_demo_user():
    out = match(DEMO_PROFILE, [REAL])
    assert [r["scheme_id"] for r in out["likely"]] == ["mp_msme_industrial_development_subsidy"]
    assert out["excluded"] == []


# --------------------------------------------------- it reaches the card

def card_for(language="en"):
    out = match(DEMO_PROFILE, [REAL], language)
    shortlist = out["matched"] + out["likely"]
    draft = {
        "summary": "s",
        "cards": [{
            "scheme_id": "mp_msme_industrial_development_subsidy",
            "name": REAL["name_en"], "what_you_get": "40% subsidy",
            "why_you_may_qualify": "new unit, manufacturing",
            "documents": [], "next_step": "office",
        }],
        "closing": "c",
    }
    return validator.validate(draft, shortlist, [REAL], language)["cards"][0]


def test_the_card_carries_a_confirm_at_the_office_list():
    assert card_for()["still_to_confirm"]


def test_the_exclusions_clause_is_named_in_that_list():
    text = " ".join(card_for()["still_to_confirm"])
    assert "7.6" in text
    assert "excluded" in text.lower()


def test_the_list_is_in_hindi_when_asked():
    text = " ".join(card_for("hi")["still_to_confirm"])
    assert "7.6" in text
    assert any("ऀ" <= ch <= "ॿ" for ch in text)


def test_the_list_comes_from_the_corpus_not_the_model():
    """The model's draft says nothing about 7.6. The clause appears anyway,
    because the validator reads it from the matcher's pending list."""
    draft = {"summary": "", "cards": [{
        "scheme_id": "mp_msme_industrial_development_subsidy",
        "name": "x", "what_you_get": "y", "why_you_may_qualify": "z",
        "documents": [], "next_step": "w",
    }], "closing": ""}
    out = match(DEMO_PROFILE, [REAL])
    card = validator.validate(draft, out["matched"] + out["likely"], [REAL])["cards"][0]
    assert any("7.6" in item for item in card["still_to_confirm"])


def test_the_model_is_told_about_it_too():
    out = match(DEMO_PROFILE, [REAL], "en")
    payload = explainer.build_input(out["matched"] + out["likely"], [REAL], "en")
    assert any("7.6" in s for s in payload["schemes"][0]["still_to_confirm"])


@pytest.mark.parametrize("language", ["en", "hi"])
def test_the_verdict_never_claims_the_clause_is_satisfied(language):
    result = evaluate_scheme(REAL, DEMO_PROFILE, language)
    assert result["verdict_text"] != "eligible"
    assert "confirm" in result["verdict_text"] or "पुष्टि" in result["reason"]
