"""Interview tests. No model, no AWS."""

from __future__ import annotations

import interview
from interview import MAX_QUESTIONS, next_question, should_stop
from tests.test_matcher import AGE, NO_UNIT, RURAL, crit, scheme


def test_asks_one_question_at_a_time():
    q = next_question({}, [scheme("a", [AGE, RURAL])])
    assert isinstance(q, dict)
    assert isinstance(q["text"], str)


def test_stops_as_soon_as_one_scheme_matches():
    """A person with an answer must not be interrogated further."""
    schemes = [scheme("a", [AGE]), scheme("b", [AGE, RURAL, NO_UNIT])]
    assert next_question({"age": 30}, schemes) is None


def test_keeps_asking_while_everything_is_only_likely():
    schemes = [scheme("a", [AGE, RURAL, NO_UNIT])]
    assert next_question({"age": 30}, schemes) is not None


def test_asks_the_most_discriminating_question_first():
    """area_type blocks three schemes, has_udyam_registration blocks one."""
    udyam = crit(criterion_id="udyam", field="has_udyam_registration",
                 test="boolean", expected=True, source_page=1)
    schemes = [
        scheme("a", [RURAL, udyam]),
        scheme("b", [RURAL]),
        scheme("c", [RURAL]),
    ]
    assert next_question({}, schemes)["field"] == "area_type"


def test_question_reports_how_many_schemes_it_unblocks():
    schemes = [scheme("a", [RURAL]), scheme("b", [RURAL])]
    assert next_question({}, schemes)["unblocks"] == 2


def test_never_asks_the_same_thing_twice():
    schemes = [scheme("a", [AGE, RURAL, NO_UNIT])]
    asked = ["area_type"]
    q = next_question({}, schemes, asked=asked)
    assert q["field"] != "area_type"


def test_never_asks_about_something_already_known():
    schemes = [scheme("a", [AGE, RURAL, NO_UNIT])]
    q = next_question({"area_type": "rural"}, schemes)
    assert q["field"] != "area_type"


def test_gives_up_after_max_questions():
    schemes = [scheme("a", [AGE, RURAL, NO_UNIT])]
    asked = ["age", "area_type", "has_existing_unit", "state"][:MAX_QUESTIONS]
    assert next_question({}, schemes, asked=asked) is None


def test_hindi_questions_are_in_hindi():
    q = next_question({}, [scheme("a", [RURAL])], language="hi")
    assert any("ऀ" <= ch <= "ॿ" for ch in q["text"])


def test_english_questions_are_in_english():
    q = next_question({}, [scheme("a", [RURAL])], language="en")
    assert not any("ऀ" <= ch <= "ॿ" for ch in q["text"])


def test_every_askable_field_has_both_languages():
    for field, text in interview.QUESTIONS.items():
        assert text["en"] and text["hi"], field


def test_questions_only_cover_real_profile_fields():
    from fields import PROFILE_FIELDS
    assert set(interview.QUESTIONS) <= set(PROFILE_FIELDS)


def test_no_schemes_means_no_questions():
    assert next_question({}, []) is None


def test_stops_when_nothing_is_left_to_ask():
    """Every pending criterion is manual, so no question could resolve them."""
    manual = crit(criterion_id="m", field="sector", test="manual", source_page=1)
    assert should_stop({"sector": "x"}, [scheme("a", [manual])]) is True


def test_full_interview_terminates():
    """Walk the loop for real and assert it ends."""
    schemes = [scheme("a", [AGE, RURAL, NO_UNIT])]
    profile, asked = {}, []
    answers = {"age": 30, "area_type": "rural", "has_existing_unit": False}

    for _ in range(MAX_QUESTIONS + 2):
        q = next_question(profile, schemes, asked=asked)
        if q is None:
            break
        asked.append(q["field"])
        if q["field"] in answers:
            profile[q["field"]] = answers[q["field"]]
    else:
        raise AssertionError("interview did not terminate")

    assert len(asked) <= MAX_QUESTIONS
