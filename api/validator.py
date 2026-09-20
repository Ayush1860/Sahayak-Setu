"""The last gate. Nothing reaches a person without passing through here.

No citation, no answer.

Every scheme_id the model wrote must be one the matcher chose. Every URL it
wrote must appear in that scheme's own source_urls. Anything else is deleted,
not flagged, not softened, not shown with a warning. Deleted.

If deleting leaves nothing, this returns the refusal: a plain statement that
we do not know, plus the official link. Never a confident guess.

Like matcher.py, this file has no model and no network. A validator that
asked a model whether the model had made something up would be worthless.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

import rates
from redact import visible, visible_list

URL_PATTERN = re.compile(r"https?://[^\s)\]\"'<>]+")

REFUSAL = {
    "en": {
        "summary": (
            "We could not find a scheme that matches what you told us. "
            "That does not mean none exists. Please ask at the office below, "
            "and take your Aadhaar and any papers about your work."
        ),
        "closing": "This is information only. Please confirm at the office.",
    },
    "hi": {
        "summary": (
            "आपने जो बताया, उसके आधार पर हमें कोई योजना नहीं मिली। "
            "इसका मतलब यह नहीं कि कोई योजना नहीं है। कृपया नीचे दिए कार्यालय में पूछें, "
            "और अपना आधार तथा काम से जुड़े कागज़ साथ ले जाएँ।"
        ),
        "closing": "यह केवल जानकारी है। कृपया कार्यालय में पुष्टि करें।",
    },
}

DISCLAIMER = {
    "en": "Information only. Confirm at the office before you act on it.",
    "hi": "यह केवल जानकारी है। कार्यालय में पुष्टि करने के बाद ही आगे बढ़ें।",
}


def allowed_sources(schemes: Sequence[dict]) -> dict[str, set[str]]:
    """scheme_id -> the URLs that scheme is permitted to cite."""
    return {
        s["scheme_id"]: {u["url"] for u in s.get("source_urls") or []}
        for s in schemes
        if s.get("scheme_id")
    }


def strip_unknown_urls(text: Any, permitted: set[str]) -> tuple[Any, list[str]]:
    """Remove any URL in free text that is not in the permitted set."""
    if not isinstance(text, str):
        return text, []
    removed: list[str] = []

    def replace(match: re.Match) -> str:
        url = match.group(0).rstrip(".,;:")
        if url in permitted:
            return match.group(0)
        removed.append(url)
        return ""

    cleaned = URL_PATTERN.sub(replace, text)
    return re.sub(r"\s{2,}", " ", cleaned).strip(), removed


def validate(
    draft: dict[str, Any],
    matched_results: Sequence[dict],
    schemes: Sequence[dict],
    language: str = "en",
    profile: dict[str, Any] | None = None,
    excluded: Sequence[dict] | None = None,
) -> dict[str, Any]:
    """Strip everything unsupported. Return a safe response, or the refusal.

    matched_results is what the matcher returned. It is the only authority on
    which schemes may appear.
    """
    lang = language if language in REFUSAL else "en"
    permitted_ids = {r["scheme_id"] for r in matched_results}
    permitted_urls = allowed_sources(schemes)
    by_id = {s.get("scheme_id"): s for s in schemes}

    kept: list[dict] = []
    dropped: list[dict] = []

    for card in draft.get("cards") or []:
        if not isinstance(card, dict):
            dropped.append({"reason": "card is not an object"})
            continue

        scheme_id = card.get("scheme_id")
        if scheme_id not in permitted_ids:
            dropped.append({
                "scheme_id": scheme_id,
                "reason": "scheme_id is not in the matched set",
            })
            continue

        allowed = permitted_urls.get(scheme_id, set())
        removed_urls: list[str] = []
        clean: dict[str, Any] = {"scheme_id": scheme_id}

        for key in ("name", "what_you_get", "why_you_may_qualify", "next_step"):
            value, removed = strip_unknown_urls(card.get(key), allowed)
            clean[key] = value
            removed_urls.extend(removed)

        clean["documents"] = visible_list(card.get("documents"))
        for key in ("name", "what_you_get", "why_you_may_qualify", "next_step"):
            clean[key] = visible(clean.get(key))

        # Citations are attached by us from the corpus, never copied from the
        # model. This is the only way a URL can reach the user.
        scheme = by_id.get(scheme_id, {})
        clean["sources"] = [
            {
                "url": u["url"],
                "title": u.get("title"),
                "retrieved_on": u.get("retrieved_on"),
            }
            for u in scheme.get("source_urls") or []
        ]
        clean["last_verified"] = (scheme.get("last_verified") or {}).get("date")

        # Things the code could not settle, taken from the matcher's pending
        # list rather than from the model. A manual criterion lands here: the
        # person is told to ask about it, and is never told it is satisfied.
        # Rate lines, selected by Python, copied verbatim, never combined.
        selected = rates.select(scheme, profile or {}, lang)
        clean["rates"] = selected["applies"]
        clean["rates_possible"] = selected["possible"]

        clean["still_to_confirm"] = visible_list([
            c.get(f"label_{lang}") or c.get("label_en")
            for r in matched_results if r["scheme_id"] == scheme_id
            for c in r.get("pending", [])
        ])
        clean["source_pages"] = sorted({
            c.get("source_page")
            for r in matched_results if r["scheme_id"] == scheme_id
            for c in r.get("reasons_met", [])
            if isinstance(c.get("source_page"), int)
        })

        if removed_urls:
            dropped.append({"scheme_id": scheme_id, "reason": "invented URLs removed", "urls": removed_urls})

        if not clean["sources"]:
            dropped.append({"scheme_id": scheme_id, "reason": "scheme has no verified source URL"})
            continue

        kept.append(clean)

    summary, removed = strip_unknown_urls(draft.get("summary"), set().union(*permitted_urls.values()) if permitted_urls else set())
    if removed:
        dropped.append({"reason": "invented URLs removed from summary", "urls": removed})

    if not kept:
        # A refusal that cannot say why is a dead end. The matcher knows
        # exactly which requirement failed, so say it: the person can then
        # tell whether it is a misunderstanding or a real disqualification,
        # and argue their case at the office.
        not_eligible = [
            {
                "name": visible(r.get(f"name_{lang}")) or visible(r.get("name_en")),
                "reason": visible(r.get("reason")),
                "source_pages": sorted({
                    f["source_page"] for f in r.get("failed", [])
                    if isinstance(f.get("source_page"), int)
                }),
            }
            for r in (excluded or [])
        ]
        return {
            "refused": True,
            "summary": REFUSAL[lang]["summary"],
            "cards": [],
            "not_eligible": [n for n in not_eligible if n["reason"]],
            "closing": REFUSAL[lang]["closing"],
            "disclaimer": DISCLAIMER[lang],
            "dropped": dropped,
        }

    return {
        "refused": False,
        "summary": summary or "",
        "cards": kept,
        "closing": draft.get("closing") or REFUSAL[lang]["closing"],
        "disclaimer": DISCLAIMER[lang],
        "dropped": dropped,
    }
