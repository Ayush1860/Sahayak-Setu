"""Unverified placeholders must never reach a user.

A partly transcribed scheme is normal and useful. Showing its gaps to a
person is not: "NOT YET VERIFIED" on a card reads as a broken system and
undermines the parts that are sound.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import explainer
from matcher import match
from redact import visible, visible_list

CORPUS = Path(__file__).resolve().parents[2] / "schemes"
REAL = json.loads((CORPUS / "mp_msme_industrial_development_subsidy.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------- the helper

@pytest.mark.parametrize("text", [
    "NOT YET VERIFIED - not stated on page 13",
    "NOT YET VERIFIED - अभी सत्यापित नहीं",
    "not yet verified",
])
def test_a_value_that_is_only_a_placeholder_is_hidden(text):
    assert visible(text) is None


def test_a_real_value_with_a_trailing_note_keeps_the_real_part():
    out = visible("District Trade and Industry Centre of your district - VERIFY THIS")
    assert out == "District Trade and Industry Centre of your district"
    assert "VERIFY" not in out


def test_hindi_marker_is_stripped_too():
    out = visible("अपने जिले का जिला व्यापार एवं उद्योग केंद्र - सत्यापित करें")
    assert out == "अपने जिले का जिला व्यापार एवं उद्योग केंद्र"


def test_ordinary_text_is_untouched():
    assert visible("40% of eligible investment") == "40% of eligible investment"


def test_a_list_of_placeholders_becomes_empty_not_a_list_of_markers():
    assert visible_list(["NOT YET VERIFIED - x", "NOT YET VERIFIED"]) == []


# --------------------------------------------------- the real scheme file

def test_the_real_scheme_carries_markers_that_must_be_hidden():
    """Guards the premise of the tests below."""
    assert "NOT YET VERIFIED" in json.dumps(REAL, ensure_ascii=False)


def test_verified_false_does_not_withhold_the_scheme():
    """PLACEHOLDER withholds. verified:false must not: the content is real."""
    out = match({"has_existing_unit": False}, [REAL])
    assert out["skipped"] == []
    assert len(out["matched"] + out["likely"]) == 1


@pytest.mark.parametrize("language", ["hi", "en"])
def test_no_marker_reaches_the_model(language):
    out = match({"has_existing_unit": False, "sector": "manufacturing",
                 "state": "madhya_pradesh"}, [REAL], language)
    payload = explainer.build_input(out["matched"] + out["likely"], [REAL], language)
    blob = json.dumps(payload, ensure_ascii=False).upper()
    assert "NOT YET VERIFIED" not in blob
    assert "VERIFY THIS" not in blob


def test_unverified_documents_become_an_empty_list_not_a_crash():
    out = match({"has_existing_unit": False}, [REAL])
    payload = explainer.build_input(out["likely"], [REAL], "en")
    assert payload["schemes"][0].get("documents", []) == []


def test_the_office_survives_with_its_verify_note_removed():
    out = match({"has_existing_unit": False}, [REAL])
    payload = explainer.build_input(out["likely"], [REAL], "en")
    office = payload["schemes"][0]["next_step"]["office"]
    assert "District Trade and Industry Centre" in office
    assert "VERIFY" not in office.upper()


def test_what_you_get_survives_intact():
    """The transcribed clause is real and must not be stripped."""
    out = match({"has_existing_unit": False}, [REAL])
    payload = explainer.build_input(out["likely"], [REAL], "en")
    assert "40%" in payload["schemes"][0]["what_you_get"]


# --------------------------------------- an answer survives a dead provider

def test_a_dead_provider_still_produces_a_card():
    """The matcher found a real scheme. A wording failure must not turn that
    into 'we found nothing'."""
    out = match({"has_existing_unit": False, "sector": "manufacturing",
                 "state": "madhya_pradesh"}, [REAL])
    shortlist = out["matched"] + out["likely"]

    draft, used_fallback = explainer.explain_or_fallback(
        shortlist, [REAL], "en", complete=lambda system, messages: {})

    assert used_fallback is True
    assert [c["scheme_id"] for c in draft["cards"]] == ["mp_msme_industrial_development_subsidy"]
    assert "40%" in draft["cards"][0]["what_you_get"]


def test_the_fallback_card_carries_no_markers():
    out = match({"has_existing_unit": False}, [REAL])
    draft, _ = explainer.explain_or_fallback(
        out["likely"], [REAL], "hi", complete=lambda system, messages: {})
    blob = json.dumps(draft, ensure_ascii=False).upper()
    assert "NOT YET VERIFIED" not in blob and "VERIFY THIS" not in blob


def test_a_working_provider_is_preferred():
    out = match({"has_existing_unit": False}, [REAL])
    good = {"summary": "s", "closing": "c", "cards": [{
        "scheme_id": "mp_msme_industrial_development_subsidy",
        "name": "n", "what_you_get": "w", "why_you_may_qualify": "y",
        "documents": [], "next_step": "o",
    }]}
    draft, used_fallback = explainer.explain_or_fallback(
        out["likely"], [REAL], "en", complete=lambda system, messages: good)
    assert used_fallback is False
    assert draft["cards"][0]["what_you_get"] == "w"
