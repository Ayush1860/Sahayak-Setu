"""Validator tests.

The centrepiece is test_hallucinated_* below: a deliberately lying model
output, proving the validator deletes what the model made up.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import validator
from validator import validate

FORBIDDEN_IMPORTS = {"boto3", "botocore", "requests", "httpx", "urllib", "anthropic", "explainer"}


def test_validator_cannot_reach_a_network():
    tree = ast.parse(Path(validator.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & FORBIDDEN_IMPORTS)


REAL_SCHEME = {
    "scheme_id": "real_scheme",
    "name_en": "Real Scheme",
    "name_hi": "असली योजना",
    "source_urls": [
        {"url": "https://real.example.gov.in/scheme", "title": "Official page", "retrieved_on": "2026-09-01"}
    ],
    "documents_required": [{"name_en": "Aadhaar", "name_hi": "आधार"}],
    "next_physical_step": {"office_en": "District office", "office_hi": "जिला कार्यालय"},
    "last_verified": {"date": "2026-09-01", "by": "Ayush"},
}

MATCHED = [{
    "scheme_id": "real_scheme",
    "verdict": "matched",
    "verdict_text": "likely eligible, confirm at the office",
    "reasons_met": [{"criterion_id": "age_range", "label_en": "Age 18 to 45", "source_page": 12}],
    "pending": [],
}]


def card(**kw):
    base = {
        "scheme_id": "real_scheme", "name": "Real Scheme",
        "what_you_get": "Help with money", "why_you_may_qualify": "You are 30",
        "documents": ["Aadhaar"], "next_step": "Go to the district office",
    }
    base.update(kw)
    return base


# ------------------------------------------------- the hallucination fixture

HALLUCINATING_OUTPUT = {
    "summary": "You may qualify for three schemes. See https://totally-made-up.example.com for more.",
    "cards": [
        card(),
        card(scheme_id="pmegp", name="PMEGP",
             what_you_get="35 percent subsidy",
             why_you_may_qualify="You are a rural entrepreneur"),
        card(scheme_id="mudra_loan", name="Mudra Loan",
             next_step="Apply at https://invented-portal.example.org/apply"),
    ],
    "closing": "Good luck!",
}


def test_hallucinated_schemes_are_deleted():
    """The model invented PMEGP and Mudra. Neither reaches the user."""
    out = validate(HALLUCINATING_OUTPUT, MATCHED, [REAL_SCHEME])
    assert [c["scheme_id"] for c in out["cards"]] == ["real_scheme"]
    reasons = {d.get("scheme_id"): d["reason"] for d in out["dropped"]}
    assert reasons["pmegp"] == "scheme_id is not in the matched set"
    assert reasons["mudra_loan"] == "scheme_id is not in the matched set"


def test_hallucinated_url_in_the_summary_is_deleted():
    out = validate(HALLUCINATING_OUTPUT, MATCHED, [REAL_SCHEME])
    assert "totally-made-up" not in out["summary"]


def test_surviving_card_keeps_its_real_content():
    out = validate(HALLUCINATING_OUTPUT, MATCHED, [REAL_SCHEME])
    kept = out["cards"][0]
    assert kept["what_you_get"] == "Help with money"
    assert kept["documents"] == ["Aadhaar"]


def test_invented_url_inside_a_valid_card_is_stripped():
    draft = {"summary": "", "cards": [card(next_step="Apply at https://fake.example.com/x")], "closing": ""}
    out = validate(draft, MATCHED, [REAL_SCHEME])
    assert "fake.example.com" not in out["cards"][0]["next_step"]
    assert any(d.get("reason") == "invented URLs removed" for d in out["dropped"])


def test_real_url_survives():
    draft = {"summary": "", "cards": [card(next_step="See https://real.example.gov.in/scheme")], "closing": ""}
    out = validate(draft, MATCHED, [REAL_SCHEME])
    assert "real.example.gov.in" in out["cards"][0]["next_step"]


# --------------------------------------------------------- citations

def test_citations_come_from_the_corpus_not_the_model():
    """Even a card with no sources gets the corpus's verified ones attached."""
    out = validate({"summary": "", "cards": [card()], "closing": ""}, MATCHED, [REAL_SCHEME])
    sources = out["cards"][0]["sources"]
    assert [s["url"] for s in sources] == ["https://real.example.gov.in/scheme"]
    assert sources[0]["retrieved_on"] == "2026-09-01"


def test_every_card_carries_a_verification_date():
    out = validate({"summary": "", "cards": [card()], "closing": ""}, MATCHED, [REAL_SCHEME])
    assert out["cards"][0]["last_verified"] == "2026-09-01"


def test_source_pages_come_from_the_criteria_that_matched():
    out = validate({"summary": "", "cards": [card()], "closing": ""}, MATCHED, [REAL_SCHEME])
    assert out["cards"][0]["source_pages"] == [12]


def test_scheme_without_a_source_url_is_dropped():
    """No citation, no answer. Even for a scheme the matcher chose."""
    unsourced = dict(REAL_SCHEME, source_urls=[])
    out = validate({"summary": "", "cards": [card()], "closing": ""}, MATCHED, [unsourced])
    assert out["refused"] is True
    assert any(d["reason"] == "scheme has no verified source URL" for d in out["dropped"])


# ------------------------------------------------------------- refusal

def test_everything_stripped_becomes_a_refusal():
    draft = {"summary": "x", "cards": [card(scheme_id="invented")], "closing": "y"}
    out = validate(draft, MATCHED, [REAL_SCHEME])
    assert out["refused"] is True
    assert out["cards"] == []
    assert "could not find" in out["summary"]


def test_refusal_is_in_hindi_when_asked():
    out = validate({"summary": "", "cards": [], "closing": ""}, [], [], language="hi")
    assert out["refused"] is True
    assert "योजना" in out["summary"]


def test_refusal_never_guesses():
    out = validate({"summary": "", "cards": [], "closing": ""}, [], [])
    assert "may qualify" not in out["summary"]
    assert "eligible" not in out["summary"].lower()


@pytest.mark.parametrize("language", ["en", "hi"])
def test_every_response_carries_a_disclaimer(language):
    out = validate({"summary": "", "cards": [card()], "closing": ""}, MATCHED, [REAL_SCHEME], language)
    assert out["disclaimer"]


def test_malformed_card_is_dropped_not_crashed():
    draft = {"summary": "", "cards": ["not a dict", None, card()], "closing": ""}
    out = validate(draft, MATCHED, [REAL_SCHEME])
    assert len(out["cards"]) == 1


def test_empty_model_output_refuses():
    out = validate({}, MATCHED, [REAL_SCHEME])
    assert out["refused"] is True
