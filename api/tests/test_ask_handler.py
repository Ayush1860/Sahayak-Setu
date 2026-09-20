"""Handler tests. Bedrock, S3 and DynamoDB are all stubbed."""

from __future__ import annotations

import json

import pytest

import ask_handler
from tests.test_matcher import AGE, RURAL, scheme


class FakeLLM:
    """Returns each canned JSON string in turn, like llm.complete would."""

    def __init__(self, *texts):
        self.texts = list(texts)

    def __call__(self, system, messages):
        text = self.texts.pop(0) if self.texts else "{}"
        return json.loads(text)


class FakeDynamo:
    def __init__(self):
        self.writes = []

    def update_item(self, **kwargs):
        self.writes.append(kwargs)


SCHEME = {
    **scheme("real_scheme", [AGE, RURAL]),
    "source_urls": [{"url": "https://x.example.gov.in/s", "title": "T", "retrieved_on": "2026-09-01"}],
    "documents_required": [{"name_en": "Aadhaar", "name_hi": "आधार"}],
    "next_physical_step": {"office_en": "Office", "office_hi": "कार्यालय"},
    "what_you_get": {"summary_en": "Help", "summary_hi": "मदद", "source_page": 1},
    "last_verified": {"date": "2026-09-01", "by": "Ayush"},
}


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    """Restores llm.complete after every test. Without this, replacing it
    leaks into other test modules and they silently stop testing anything."""
    import llm

    monkeypatch.setattr(ask_handler, "load_schemes", lambda: [SCHEME])
    monkeypatch.setattr(ask_handler, "COUNTER_TABLE", "")
    monkeypatch.setattr(llm, "complete", llm.complete)
    yield


def call(body, fake_llm):
    import ask_handler as h
    import llm

    llm.complete = fake_llm          # every caller defaults to llm.complete
    return h.handler({"body": json.dumps(body), "httpMethod": "POST"})


def body_of(response):
    return json.loads(response["body"])


# ---------------------------------------------------------------- plumbing

def test_missing_conversation_is_a_400():
    assert call({}, FakeLLM())["statusCode"] == 400


def test_bad_json_is_a_400():
    import ask_handler as h
    assert h.handler({"body": "not json", "httpMethod": "POST"})["statusCode"] == 400


def test_options_preflight_returns_cors_headers():
    import ask_handler as h
    r = h.handler({"httpMethod": "OPTIONS"})
    assert r["statusCode"] == 200
    assert "Access-Control-Allow-Origin" in r["headers"]


def test_every_response_has_cors_headers():
    r = call({"conversation": [{"role": "user", "text": "hi"}]}, FakeLLM('{"profile": {}}'))
    assert r["headers"]["Access-Control-Allow-Origin"]


# ---------------------------------------------------------------- the flow

def test_incomplete_profile_returns_one_question():
    r = call({"conversation": [{"role": "user", "text": "hello"}]}, FakeLLM('{"profile": {}}'))
    out = body_of(r)
    assert out["type"] == "question"
    assert isinstance(out["question"], str)
    assert out["asked"] == [out["field"]]


def test_complete_profile_returns_an_answer():
    draft = json.dumps({
        "summary": "You may qualify for one scheme.",
        "cards": [{"scheme_id": "real_scheme", "name": "S", "what_you_get": "Help",
                   "why_you_may_qualify": "You are 30", "documents": ["Aadhaar"],
                   "next_step": "Go to the office"}],
        "closing": "Confirm at the office.",
    })
    r = call(
        {"conversation": [{"role": "user", "text": "I am 30 and live in a village"}]},
        FakeLLM('{"profile": {"age": 30, "area_type": "rural"}}', draft),
    )
    out = body_of(r)
    assert out["type"] == "answer"
    assert out["refused"] is False
    assert [c["scheme_id"] for c in out["cards"]] == ["real_scheme"]


def test_hallucinated_scheme_is_stripped_end_to_end():
    """The validator runs inside the handler, not as an afterthought."""
    draft = json.dumps({
        "summary": "Two schemes.",
        "cards": [
            {"scheme_id": "real_scheme", "name": "S", "what_you_get": "Help",
             "why_you_may_qualify": "You are 30", "documents": [], "next_step": "Office"},
            {"scheme_id": "pmegp", "name": "PMEGP", "what_you_get": "35 percent",
             "why_you_may_qualify": "invented", "documents": [], "next_step": "invented"},
        ],
        "closing": "",
    })
    r = call(
        {"conversation": [{"role": "user", "text": "I am 30, village"}]},
        FakeLLM('{"profile": {"age": 30, "area_type": "rural"}}', draft),
    )
    out = body_of(r)
    assert [c["scheme_id"] for c in out["cards"]] == ["real_scheme"]


def test_answer_carries_a_disclaimer_and_citations():
    draft = json.dumps({
        "summary": "s", "closing": "c",
        "cards": [{"scheme_id": "real_scheme", "name": "S", "what_you_get": "Help",
                   "why_you_may_qualify": "r", "documents": [], "next_step": "Office"}],
    })
    out = body_of(call(
        {"conversation": [{"role": "user", "text": "I am 30, village"}]},
        FakeLLM('{"profile": {"age": 30, "area_type": "rural"}}', draft),
    ))
    assert out["disclaimer"]
    assert out["cards"][0]["sources"][0]["url"] == "https://x.example.gov.in/s"
    assert out["cards"][0]["last_verified"] == "2026-09-01"


def test_hindi_conversation_answers_in_hindi():
    out = body_of(call(
        {"conversation": [{"role": "user", "text": "मैं दोना पत्तल बनाता हूँ"}]},
        FakeLLM('{"profile": {}}'),
    ))
    assert out["language"] == "hi"
    assert any("ऀ" <= ch <= "ॿ" for ch in out["question"])


# ---------------------------------------------------------------- privacy

def test_counters_never_receive_anything_about_a_person(monkeypatch):
    fake = FakeDynamo()
    monkeypatch.setattr(ask_handler, "COUNTER_TABLE", "counters")
    monkeypatch.setattr(ask_handler, "dynamo", lambda: fake)

    call({"conversation": [{"role": "user", "text": "I am 30 and earn 50000 a year"}]},
         FakeLLM('{"profile": {"age": 30, "annual_income_inr": 50000}}'))

    written = json.dumps(fake.writes)
    for forbidden in ("30", "50000", "earn", "age", "income", "caste", "gender"):
        assert forbidden not in written, f"{forbidden!r} reached DynamoDB"


def test_a_counter_failure_does_not_break_the_answer(monkeypatch):
    class Broken:
        def update_item(self, **kwargs):
            raise RuntimeError("dynamo is down")

    monkeypatch.setattr(ask_handler, "COUNTER_TABLE", "counters")
    monkeypatch.setattr(ask_handler, "dynamo", lambda: Broken())

    r = call({"conversation": [{"role": "user", "text": "hello"}]}, FakeLLM('{"profile": {}}'))
    assert r["statusCode"] == 200


def test_the_response_never_names_the_provider_or_model(monkeypatch):
    """describe() is for logs. A browser must not learn which model ran."""
    import llm

    monkeypatch.setattr(llm, "GROQ_MODEL", "some-secret-model-name")
    monkeypatch.setattr(llm, "PROVIDER", "groq")

    r = call({"conversation": [{"role": "user", "text": "hello"}]}, FakeLLM('{"profile": {}}'))
    body = r["body"].lower()
    for leak in ("groq", "bedrock", "llm", "provider", "some-secret-model-name", "anthropic"):
        assert leak not in body, f"{leak!r} leaked to the browser"


def test_a_question_carries_its_tap_options():
    """The interview computes options; the handler must forward them, or the
    browser silently falls back to a text box nobody can use."""
    r = call({"conversation": [{"role": "user", "text": "hello"}]}, FakeLLM('{"profile": {}}'))
    out = body_of(r)
    assert out["type"] == "question"
    assert out["input_type"] in ("choice", "range", "select", "text")
    if out["input_type"] != "text":
        assert out["options"], "a non-text question must offer options"
        assert all("label" in o for o in out["options"])


def test_tapped_answers_reach_the_profile_without_the_model():
    """A provider outage must not break the interview: an explicit choice is
    data in its own right."""
    r = call({"conversation": [{"role": "user", "text": "hi"}],
              "answers": {"has_existing_unit": False, "area_type": "rural"}},
             FakeLLM('{"profile": {}}'))
    out = body_of(r)
    assert out["type"] in ("question", "answer")
    if out["type"] == "question":
        assert out["field"] not in ("has_existing_unit", "area_type")
