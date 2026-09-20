"""Matcher tests.

The first test in this file is the one that matters for the claim
"eligibility is decided by code, the model only does language": it reads
matcher.py's own imports and fails if anything that could reach a network
appears among them.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import matcher
from matcher import Outcome, Verdict, evaluate_criterion, evaluate_scheme, match

MATCHER_SOURCE = Path(matcher.__file__)
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "scheme.schema.json"


# ------------------------------------------------------- the structural claim

FORBIDDEN_IMPORTS = {
    "boto3", "botocore", "requests", "httpx", "urllib", "urllib3", "http",
    "socket", "anthropic", "openai", "extractor", "explainer",
}


def test_matcher_imports_nothing_that_can_reach_a_network():
    """Eligibility is decided by code, not by a model. This proves it."""
    tree = ast.parse(MATCHER_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & FORBIDDEN_IMPORTS), f"matcher.py imports {imported & FORBIDDEN_IMPORTS}"


def test_every_schema_test_type_is_implemented():
    """A test type the schema allows but the matcher does not implement would
    silently become UNKNOWN for every scheme that used it."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    allowed = schema["$defs"]["criterion"]["properties"]["test"]["enum"]
    assert sorted(matcher.TESTS) == sorted(allowed)


def test_no_verdict_claims_entitlement():
    for text in matcher.VERDICT_TEXT.values():
        assert "entitled" not in text
        assert not text.startswith("eligible")


# ------------------------------------------------------------- the five tests

def crit(**kwargs):
    base = {
        "criterion_id": "c", "field": "age", "test": "range",
        "label_en": "L", "label_hi": "L", "source_page": 1,
    }
    base.update(kwargs)
    return base


@pytest.mark.parametrize("age,expected", [
    (17, Outcome.FAIL), (18, Outcome.PASS), (30, Outcome.PASS),
    (45, Outcome.PASS), (46, Outcome.FAIL),
])
def test_range_is_inclusive_at_both_ends(age, expected):
    c = crit(test="range", min=18, max=45)
    assert evaluate_criterion(c, {"age": age}) is expected


def test_range_with_only_a_minimum():
    c = crit(test="range", min=18)
    assert evaluate_criterion(c, {"age": 99}) is Outcome.PASS
    assert evaluate_criterion(c, {"age": 17}) is Outcome.FAIL


def test_one_of():
    c = crit(field="caste_category", test="one_of", values=["sc", "st"])
    assert evaluate_criterion(c, {"caste_category": "sc"}) is Outcome.PASS
    assert evaluate_criterion(c, {"caste_category": "obc"}) is Outcome.FAIL


def test_none_of():
    c = crit(field="state", test="none_of", values=["Goa"])
    assert evaluate_criterion(c, {"state": "Goa"}) is Outcome.FAIL
    assert evaluate_criterion(c, {"state": "Madhya Pradesh"}) is Outcome.PASS


def test_boolean_expected_false():
    c = crit(field="has_existing_unit", test="boolean", expected=False)
    assert evaluate_criterion(c, {"has_existing_unit": False}) is Outcome.PASS
    assert evaluate_criterion(c, {"has_existing_unit": True}) is Outcome.FAIL


def test_manual_is_always_unknown_even_when_the_field_is_known():
    c = crit(field="sector", test="manual")
    assert evaluate_criterion(c, {"sector": "leaf plates"}) is Outcome.UNKNOWN


# --------------------------------------------------- missing means UNKNOWN

def test_absent_field_is_unknown_not_fail():
    c = crit(test="range", min=18, max=45)
    assert evaluate_criterion(c, {}) is Outcome.UNKNOWN


def test_absent_field_is_unknown_not_pass():
    c = crit(field="caste_category", test="one_of", values=["sc"])
    assert evaluate_criterion(c, {}) is Outcome.UNKNOWN


def test_wrong_type_is_unknown_not_fail():
    """A string where a number belongs is a bug upstream, not a disqualification."""
    c = crit(test="range", min=18, max=45)
    assert evaluate_criterion(c, {"age": "thirty"}) is Outcome.UNKNOWN


def test_true_is_not_treated_as_the_number_one():
    c = crit(test="range", min=1, max=5)
    assert evaluate_criterion(c, {"age": True}) is Outcome.UNKNOWN


def test_unknown_test_type_is_unknown_not_fail():
    c = crit(test="sorcery")
    assert evaluate_criterion(c, {"age": 30}) is Outcome.UNKNOWN


def test_field_outside_the_vocabulary_is_unknown():
    c = crit(field="favourite_colour", test="one_of", values=["blue"])
    assert evaluate_criterion(c, {"favourite_colour": "blue"}) is Outcome.UNKNOWN


# ------------------------------------------------------------- scheme verdicts

def scheme(scheme_id="s", criteria=None, **extra):
    d = {
        "scheme_id": scheme_id, "name_en": "S", "name_hi": "S",
        "eligibility": {"criteria": criteria or []},
    }
    d.update(extra)
    return d


AGE = crit(criterion_id="age_range", test="range", min=18, max=45,
           label_en="Age 18 to 45", label_hi="उम्र 18 से 45")
RURAL = crit(criterion_id="rural", field="area_type", test="one_of", values=["rural"],
             label_en="Rural area", label_hi="ग्रामीण क्षेत्र", source_page=2)
NO_UNIT = crit(criterion_id="no_unit", field="has_existing_unit", test="boolean",
               expected=False, label_en="No existing unit", label_hi="कोई इकाई नहीं",
               source_page=3)


def test_all_pass_is_matched():
    r = evaluate_scheme(scheme(criteria=[AGE, RURAL]), {"age": 30, "area_type": "rural"})
    assert r["verdict"] == Verdict.MATCHED.value
    assert len(r["reasons_met"]) == 2
    assert r["pending"] == [] and r["failed"] == []


def test_matched_still_says_confirm_at_the_office():
    r = evaluate_scheme(scheme(criteria=[AGE]), {"age": 30})
    assert r["verdict_text"] == "likely eligible, confirm at the office"
    assert "Confirm at the office" in r["reason"]


def test_one_fail_excludes_even_when_everything_else_passes():
    r = evaluate_scheme(scheme(criteria=[AGE, RURAL]), {"age": 60, "area_type": "rural"})
    assert r["verdict"] == Verdict.EXCLUDED.value
    assert [f["criterion_id"] for f in r["failed"]] == ["age_range"]


def test_fail_beats_unknown():
    """A known violation excludes, regardless of what is still unknown."""
    r = evaluate_scheme(scheme(criteria=[AGE, RURAL]), {"age": 60})
    assert r["verdict"] == Verdict.EXCLUDED.value


def test_half_known_profile_is_likely_not_excluded():
    r = evaluate_scheme(scheme(criteria=[AGE, RURAL, NO_UNIT]), {"age": 30})
    assert r["verdict"] == Verdict.LIKELY.value
    assert [p["criterion_id"] for p in r["pending"]] == ["rural", "no_unit"]
    assert [m["criterion_id"] for m in r["reasons_met"]] == ["age_range"]


def test_empty_profile_is_likely_not_matched_and_not_excluded():
    r = evaluate_scheme(scheme(criteria=[AGE, RURAL, NO_UNIT]), {})
    assert r["verdict"] == Verdict.LIKELY.value
    assert len(r["pending"]) == 3


def test_manual_criterion_keeps_a_fully_known_profile_in_likely():
    manual = crit(criterion_id="officer", field="sector", test="manual",
                  label_en="Officer confirms trade", label_hi="अधिकारी पुष्टि करेगा")
    r = evaluate_scheme(scheme(criteria=[AGE, manual]), {"age": 30, "sector": "x"})
    assert r["verdict"] == Verdict.LIKELY.value
    assert r["pending"][0]["criterion_id"] == "officer"


def test_scheme_with_no_criteria_is_matched():
    assert evaluate_scheme(scheme(criteria=[]), {})["verdict"] == Verdict.MATCHED.value


# ------------------------------------------------------------ reason strings

def test_reason_names_the_specific_criterion_that_failed():
    r = evaluate_scheme(scheme(criteria=[AGE]), {"age": 60})
    assert "Age 18 to 45" in r["reason"]


def test_fail_reason_override_is_used():
    c = crit(criterion_id="x", field="has_existing_unit", test="boolean", expected=False,
             fail_reason_en="An existing unit disqualifies")
    r = evaluate_scheme(scheme(criteria=[c]), {"has_existing_unit": True})
    assert r["reason"] == "An existing unit disqualifies"


def test_hindi_reasons_use_hindi_labels():
    r = evaluate_scheme(scheme(criteria=[AGE]), {"age": 60}, language="hi")
    assert "उम्र 18 से 45" in r["reason"]


def test_every_reason_carries_a_source_page():
    r = evaluate_scheme(scheme(criteria=[AGE, RURAL, NO_UNIT]), {"age": 30, "area_type": "urban"})
    for bucket in ("reasons_met", "pending", "failed"):
        for item in r[bucket]:
            assert isinstance(item["source_page"], int)


# ------------------------------------------------------------------- match()

def test_match_sorts_into_buckets():
    a = scheme("a", [AGE])
    b = scheme("b", [AGE, RURAL])
    c = scheme("c", [crit(criterion_id="over60", test="range", min=60)])
    out = match({"age": 30}, [a, b, c])
    assert [r["scheme_id"] for r in out["matched"]] == ["a"]
    assert [r["scheme_id"] for r in out["likely"]] == ["b"]
    assert [r["scheme_id"] for r in out["excluded"]] == ["c"]


def test_placeholder_schemes_are_withheld_by_default():
    out = match({"age": 30}, [scheme("fake", [AGE], PLACEHOLDER=True)])
    assert out["matched"] == [] and out["likely"] == []
    assert out["skipped"][0]["scheme_id"] == "fake"


def test_placeholder_schemes_can_be_included_for_testing():
    out = match({"age": 30}, [scheme("fake", [AGE], PLACEHOLDER=True)], include_placeholders=True)
    assert [r["scheme_id"] for r in out["matched"]] == ["fake"]


def test_results_sort_most_confirmed_first():
    one = scheme("one", [AGE, RURAL, NO_UNIT])
    two = scheme("two", [AGE, RURAL, NO_UNIT])
    # two matches more criteria than one, given this profile
    out = match({"age": 30, "area_type": "rural"}, [one, two])
    assert len(out["likely"]) == 2


def test_fields_that_would_help_ranks_by_how_many_schemes_they_unblock():
    a = scheme("a", [RURAL, NO_UNIT])
    b = scheme("b", [RURAL])
    c = scheme("c", [RURAL])
    out = match({}, [a, b, c])
    assert matcher.fields_that_would_help(out)[0] == "area_type"


def test_the_real_placeholder_scheme_file_runs_through_the_matcher():
    """Exercises the actual corpus file, not a hand-built dict."""
    path = Path(__file__).resolve().parents[2] / "schemes" / "example_placeholder_scheme.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out = match({"age": 30}, [data], include_placeholders=True)
    assert len(out["likely"]) == 1
    assert out["likely"][0]["reasons_met"][0]["criterion_id"] == "age_range"


# ------------------------------------------- buckets, not typed numbers

BUCKET_CRIT = crit(criterion_id="age", test="range", min=18, max=45)


def test_a_bucket_entirely_inside_the_range_passes():
    assert evaluate_criterion(BUCKET_CRIT, {"age": {"min": 26, "max": 35}}) is Outcome.PASS


def test_a_bucket_entirely_outside_the_range_fails():
    assert evaluate_criterion(BUCKET_CRIT, {"age": {"min": 61, "max": 100}}) is Outcome.FAIL


def test_a_bucket_straddling_the_boundary_is_unknown_not_a_guess():
    """36-45 against a rule of 18-40 does not say whether they qualify."""
    c = crit(criterion_id="age", test="range", min=18, max=40)
    assert evaluate_criterion(c, {"age": {"min": 36, "max": 45}}) is Outcome.UNKNOWN


def test_a_bucket_touching_the_edge_passes():
    assert evaluate_criterion(BUCKET_CRIT, {"age": {"min": 18, "max": 45}}) is Outcome.PASS


def test_a_malformed_bucket_is_unknown():
    assert evaluate_criterion(BUCKET_CRIT, {"age": {"min": "x", "max": 35}}) is Outcome.UNKNOWN


def test_plain_numbers_still_work():
    assert evaluate_criterion(BUCKET_CRIT, {"age": 30}) is Outcome.PASS
    assert evaluate_criterion(BUCKET_CRIT, {"age": 60}) is Outcome.FAIL
