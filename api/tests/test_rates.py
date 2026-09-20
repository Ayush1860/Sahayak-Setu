"""Task B: Python selects rate lines. Nothing computes a total.

The demo turns on this: the interview asks caste category and gender, and
the card gains a line citing page 13. What it must never do is gain a number
that nobody wrote down.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import rates
import validator
from matcher import match

CORPUS = Path(__file__).resolve().parents[2] / "schemes"
REAL = json.loads((CORPUS / "mp_msme_industrial_development_subsidy.json").read_text(encoding="utf-8"))

BASE_PROFILE = {
    "has_existing_unit": False,
    "sector": "manufacturing",
    "state": "madhya_pradesh",
    "area_type": "rural",
    "age": 32,
}


def ids(selected):
    return [s["modifier_id"] for s in selected]


# ------------------------------------------------- no arithmetic, anywhere

def test_rates_module_contains_no_arithmetic():
    """A totals bug here would misstate how much money someone receives."""
    tree = ast.parse(Path(rates.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp):
            assert not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)), \
                "arithmetic in rates.py"


def test_no_selected_rate_is_a_number_we_produced():
    """Every string returned must appear verbatim in the scheme file."""
    out = rates.select(REAL, dict(BASE_PROFILE, caste_category="sc", gender="female"))
    written = {m["rate_en"] for m in REAL["rate_modifiers"]}
    for entry in out["applies"] + out["possible"]:
        assert entry["rate"] in written


def test_the_combined_figure_never_appears():
    out = rates.select(REAL, dict(BASE_PROFILE, caste_category="sc", gender="female"))
    blob = json.dumps(out)
    # "50%" legitimately appears in the export condition text, so only
    # totals that nobody wrote down are forbidden.
    for invented in ("42.5", "52.5", "45%"):
        assert invented not in blob


# ------------------------------------------------------------- selection

def test_base_always_applies():
    assert "base" in ids(rates.select(REAL, {})["applies"])


def test_nothing_extra_applies_to_a_general_category_man():
    out = rates.select(REAL, dict(BASE_PROFILE, caste_category="general", gender="male"))
    assert ids(out["applies"]) == ["base"]


def test_a_woman_gets_the_women_sc_st_line():
    out = rates.select(REAL, dict(BASE_PROFILE, caste_category="general", gender="female"))
    assert "women_sc_st" in ids(out["applies"])
    assert "sc_st_women" not in ids(out["applies"])


def test_an_sc_man_gets_the_women_sc_st_line():
    out = rates.select(REAL, dict(BASE_PROFILE, caste_category="sc", gender="male"))
    assert "women_sc_st" in ids(out["applies"])


def test_an_sc_woman_gets_the_more_specific_line():
    out = rates.select(REAL, dict(BASE_PROFILE, caste_category="sc", gender="female"))
    assert "sc_st_women" in ids(out["applies"])


def test_unknown_caste_and_gender_make_the_lines_possible_not_applied():
    """Before the interview asks, nothing is claimed either way."""
    out = rates.select(REAL, BASE_PROFILE)
    assert ids(out["applies"]) == ["base"]
    assert "women_sc_st" in ids(out["possible"])


def test_export_modifiers_are_always_only_possible():
    """No profile field records export share, so they can never be asserted."""
    out = rates.select(REAL, dict(BASE_PROFILE, caste_category="sc", gender="female"))
    assert "export_25_50" in ids(out["possible"])
    assert "export_25_50" not in ids(out["applies"])


def test_every_rate_line_carries_its_page():
    out = rates.select(REAL, dict(BASE_PROFILE, caste_category="sc", gender="female"))
    for entry in out["applies"]:
        assert entry["source_page"] == 13


# ------------------------------------------- the demo: the card changes

def card_for(profile, language="en"):
    out = match(profile, [REAL], language)
    shortlist = out["matched"] + out["likely"]
    draft = {"summary": "s", "closing": "c", "cards": [{
        "scheme_id": "mp_msme_industrial_development_subsidy",
        "name": REAL["name_en"], "what_you_get": "subsidy",
        "why_you_may_qualify": "r", "documents": [], "next_step": "office",
    }]}
    return validator.validate(draft, shortlist, [REAL], language, profile)["cards"][0]


def test_the_card_gains_a_line_when_caste_and_gender_are_known():
    before = card_for(BASE_PROFILE)
    after = card_for(dict(BASE_PROFILE, caste_category="sc", gender="female"))
    assert len(after["rates"]) > len(before["rates"])
    assert "2.5%" in " ".join(r["rate"] for r in after["rates"])


def test_the_base_rate_is_still_shown_alongside_it():
    card = card_for(dict(BASE_PROFILE, caste_category="sc", gender="female"))
    assert "40%" in " ".join(r["rate"] for r in card["rates"])


def test_rates_come_from_the_corpus_not_the_model():
    """The model's draft mentions no percentage at all."""
    card = card_for(dict(BASE_PROFILE, caste_category="sc", gender="female"))
    assert card["rates"]


@pytest.mark.parametrize("language", ["en", "hi"])
def test_the_card_never_shows_a_total(language):
    card = card_for(dict(BASE_PROFILE, caste_category="sc", gender="female"), language)
    blob = json.dumps(card, ensure_ascii=False)
    assert "42.5" not in blob
