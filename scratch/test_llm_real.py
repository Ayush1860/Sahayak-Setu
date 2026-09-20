"""One real end-to-end run against the configured provider.

    $env:GROQ_API_KEY = "gsk_..."
    python scratch/test_llm_real.py

Nothing in this codebase has ever called a real model. Both prompts were
written against a stub, so this is where prompt problems surface. It checks
the two things that actually matter:

    the extractor returns fields, and invents nothing
    the explainer writes cards, and does no arithmetic

Output goes to scratch/real_run.txt as UTF-8, because Windows consoles
cannot print Devanagari.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

import ask_handler  # noqa: E402
import explainer  # noqa: E402
import extractor  # noqa: E402
import llm  # noqa: E402
import rates  # noqa: E402
import validator  # noqa: E402
from matcher import match  # noqa: E402

OUT = ROOT / "scratch" / "real_run.txt"

HINDI = "मैं मध्य प्रदेश के गाँव में दोना पत्तल बनाती हूँ, उम्र 32, अभी कोई इकाई नहीं है"
ENGLISH = "I make leaf plates at home in my village in Madhya Pradesh. I am 32 and have no unit yet."

# Things the model must not invent. A leaf-plate maker never stated a caste,
# an income, or a Udyam registration.
NEVER_INVENT = ("caste_category", "annual_income_inr", "has_udyam_registration")

# Totals nobody wrote down.
FORBIDDEN_NUMBERS = ("42.5", "52.5", "45%")


def load_corpus() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((ROOT / "schemes").glob("*.json"))
    ]


def main() -> int:
    log = io.StringIO()
    problems: list[str] = []

    def say(line: str = "") -> None:
        log.write(line + "\n")

    if llm.PROVIDER == "groq" and not llm.GROQ_API_KEY:
        print("GROQ_API_KEY is not set. Nothing was called.", file=sys.stderr)
        return 1

    say(f"provider={llm.PROVIDER} model={llm.describe()['model']}")
    say("=" * 70)

    schemes = load_corpus()

    # ---------------------------------------------------------- extractor
    for label, text in (("hindi", HINDI), ("english", ENGLISH)):
        say(f"\n--- extractor, {label}")
        say(f"input: {text}")
        result = extractor.extract([{"role": "user", "text": text}])
        say(f"language: {result['language']}")
        say(f"profile: {json.dumps(result['profile'], ensure_ascii=False)}")
        say(f"missing: {result['missing']}")

        if not result["profile"]:
            problems.append(f"{label}: extractor returned an empty profile")
        if label == "hindi" and result["language"] != "hi":
            problems.append("hindi input was not detected as Hindi")
        for field in NEVER_INVENT:
            if field in result["profile"]:
                problems.append(f"{label}: invented {field}={result['profile'][field]!r}")
        if result["profile"].get("sector") not in (None, "manufacturing"):
            problems.append(f"{label}: sector classified as {result['profile']['sector']!r}")

    # ---------------------------------------------------------- explainer
    profile = {
        "has_existing_unit": False, "sector": "manufacturing",
        "state": "madhya_pradesh", "area_type": "rural", "age": 32,
        "caste_category": "sc", "gender": "female",
    }

    for language in ("hi", "en"):
        say(f"\n--- explainer, {language}")
        results = match(profile, schemes, language)
        shortlist = results["matched"] + results["likely"]
        if not shortlist:
            problems.append("matcher returned nothing for the demo profile")
            continue

        draft = explainer.explain(shortlist, schemes, language, profile=profile)
        answer = validator.validate(draft, shortlist, schemes, language, profile)

        say(f"refused: {answer['refused']}")
        say(f"summary: {answer.get('summary', '')}")
        for card in answer["cards"]:
            say(f"  name: {card.get('name')}")
            say(f"  what_you_get: {(card.get('what_you_get') or '')[:200]}")
            say(f"  why: {card.get('why_you_may_qualify')}")
            say(f"  rates: {[r['rate'] for r in card.get('rates', [])]}")
            say(f"  confirm: {card.get('still_to_confirm')}")
        say(f"dropped: {json.dumps(answer.get('dropped', []), ensure_ascii=False)}")

        if not draft.get("cards"):
            problems.append(f"{language}: explainer produced no cards")
        if answer["refused"]:
            problems.append(f"{language}: validator refused a matched scheme")

        blob = json.dumps(answer, ensure_ascii=False)
        for number in FORBIDDEN_NUMBERS:
            if number in blob:
                problems.append(f"{language}: a computed total {number!r} reached the output")
        if answer.get("dropped"):
            problems.append(f"{language}: validator dropped something, see the log")
        if language == "hi" and answer["cards"]:
            text = (answer["cards"][0].get("why_you_may_qualify") or "")
            if text and not any("ऀ" <= ch <= "ॿ" for ch in text):
                problems.append("hindi card was written in English")

    # ------------------------------------------------------------- report
    say("\n" + "=" * 70)
    if problems:
        say(f"{len(problems)} PROBLEM(S):")
        for p in problems:
            say(f"  - {p}")
    else:
        say("no problems found")

    OUT.write_text(log.getvalue(), encoding="utf-8")
    print(f"written to {OUT}")
    print(f"{len(problems)} problem(s)" if problems else "no problems found")
    for p in problems:
        print(f"  - {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
