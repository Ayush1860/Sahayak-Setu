"""Turn matched schemes into readable cards. The second and last model call.

The model receives only schemes the matcher already chose, and only the
fields it is allowed to talk about. It decides nothing. Whatever it writes
goes through validator.py before anyone sees it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Sequence

import llm
import rates
from redact import visible, visible_list

PROMPT_PATH = Path(__file__).parent / "prompts" / "explainer_system.txt"


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_input(results: Sequence[dict], schemes: Sequence[dict], language: str,
                profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Exactly what the model is allowed to see. Nothing else from the corpus.

    Building this explicitly, rather than passing whole scheme dicts, is what
    keeps the model from quoting a field nobody verified.
    """
    by_id = {s.get("scheme_id"): s for s in schemes}
    payload = []

    for result in results:
        scheme = by_id.get(result["scheme_id"])
        if not scheme:
            continue
        lang = language if language in ("hi", "en") else "en"
        step = scheme.get("next_physical_step") or {}
        entry = {
            "scheme_id": scheme["scheme_id"],
            "name": visible(scheme.get(f"name_{lang}")) or visible(scheme.get("name_en")),
            "what_you_get": visible((scheme.get("what_you_get") or {}).get(f"summary_{lang}")),
            "criteria_met": visible_list(
                [c.get(f"label_{lang}") or c.get("label_en") for c in result["reasons_met"]]
            ),
            "still_to_confirm": visible_list(
                [c.get(f"label_{lang}") or c.get("label_en") for c in result.get("pending", [])]
            ),
            "documents": visible_list(
                [d.get(f"name_{lang}") or d.get("name_en")
                 for d in scheme.get("documents_required") or []]
            ),
            "next_step": {
                "office": visible(step.get(f"office_{lang}")) or visible(step.get("office_en")),
                "what_to_carry": visible(step.get(f"what_to_carry_{lang}")),
            },
            "sources": [u["url"] for u in scheme.get("source_urls") or []],
            "verdict": result["verdict_text"],
        }
        selected = rates.select(scheme, profile or {}, lang)
        if selected["applies"]:
            entry["rate_lines"] = rates.as_strings(selected["applies"])
        if disbursement := visible((scheme.get("disbursement") or {}).get(f"summary_{lang}")
                                   or (scheme.get("disbursement") or {}).get("summary_en")):
            entry["disbursement"] = disbursement
        payload.append({k: v for k, v in entry.items() if v not in (None, [], {})})

    return {"language": language, "schemes": payload}


def explain(
    results: Sequence[dict],
    schemes: Sequence[dict],
    language: str = "en",
    complete: Callable[..., dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the model's draft. Not safe to show until validator.py has run."""
    complete = complete or llm.complete
    payload = build_input(results, schemes, language, profile)
    message = [{"role": "user", "text": json.dumps(payload, ensure_ascii=False)}]
    return complete(load_system_prompt(), message) or {"summary": "", "cards": [], "closing": ""}


def fallback_cards(payload: dict[str, Any]) -> dict[str, Any]:
    """Cards assembled from the corpus, with no model involved.

    Used when the provider is unreachable or returns nothing usable. The
    wording is plainer than a model would manage, because every string is
    copied from the scheme file rather than rewritten.

    This is not a guess. The matcher already decided these schemes apply and
    every sentence here was transcribed by a human from the source document.
    Refusing at this point would throw away a real answer over a wording
    problem, and tell someone "we found nothing" when we found something.
    """
    hindi = payload.get("language") == "hi"
    cards = []

    for scheme in payload.get("schemes", []):
        met = [c for c in scheme.get("criteria_met") or [] if c]
        step = scheme.get("next_step") or {}
        cards.append({
            "scheme_id": scheme["scheme_id"],
            "name": scheme.get("name"),
            "what_you_get": scheme.get("what_you_get"),
            "why_you_may_qualify": "; ".join(met),
            "documents": scheme.get("documents") or [],
            "next_step": " ".join(
                x for x in (step.get("office"), step.get("what_to_carry")) if x
            ),
        })

    count = len(cards)
    if hindi:
        summary = f"आपने जो बताया, उसके आधार पर {count} योजना मिली है।"
        closing = "यह केवल जानकारी है। कार्यालय में पुष्टि ज़रूर करें।"
    else:
        summary = f"Based on what you told us, we found {count} scheme(s) that may apply."
        closing = "This is information only. Please confirm at the office."

    return {"summary": summary, "cards": cards, "closing": closing}


def explain_or_fallback(
    results: Sequence[dict],
    schemes: Sequence[dict],
    language: str = "en",
    complete: Callable[..., dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Returns (draft, used_fallback)."""
    payload = build_input(results, schemes, language, profile)
    complete = complete or llm.complete
    draft = complete(load_system_prompt(),
                     [{"role": "user", "text": json.dumps(payload, ensure_ascii=False)}]) or {}
    if draft.get("cards"):
        return draft, False
    return fallback_cards(payload), True
