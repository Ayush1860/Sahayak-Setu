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

PROMPT_PATH = Path(__file__).parent / "prompts" / "explainer_system.txt"


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_input(results: Sequence[dict], schemes: Sequence[dict], language: str) -> dict[str, Any]:
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
        payload.append({
            "scheme_id": scheme["scheme_id"],
            "name": scheme.get(f"name_{lang}") or scheme.get("name_en"),
            "what_you_get": (scheme.get("what_you_get") or {}).get(f"summary_{lang}"),
            "criteria_met": [c.get(f"label_{lang}") or c.get("label_en") for c in result["reasons_met"]],
            "still_to_confirm": [c.get(f"label_{lang}") or c.get("label_en") for c in result.get("pending", [])],
            "documents": [
                d.get(f"name_{lang}") or d.get("name_en")
                for d in scheme.get("documents_required") or []
            ],
            "next_step": {
                "office": (scheme.get("next_physical_step") or {}).get(f"office_{lang}"),
                "what_to_carry": (scheme.get("next_physical_step") or {}).get(f"what_to_carry_{lang}"),
            },
            "sources": [u["url"] for u in scheme.get("source_urls") or []],
            "verdict": result["verdict_text"],
        })

    return {"language": language, "schemes": payload}


def explain(
    results: Sequence[dict],
    schemes: Sequence[dict],
    language: str = "en",
    complete: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the model's draft. Not safe to show until validator.py has run."""
    complete = complete or llm.complete
    payload = build_input(results, schemes, language)
    message = [{"role": "user", "text": json.dumps(payload, ensure_ascii=False)}]
    return complete(load_system_prompt(), message) or {"summary": "", "cards": [], "closing": ""}
