"""Run the real pipeline locally with no model and no AWS.

    python scratch/dev_server.py

This is a demo harness, not part of the app. It exists so the frontend can be
clicked through before a provider is reachable.

What is real: every line of extractor, interview, matcher, explainer and
validator runs exactly as it does in Lambda. The interview order, the three
valued logic, the citation stripping and the refusal are all genuine.

What is faked: llm.complete is replaced by deterministic Python, because
Bedrock is blocked account wide and Groq needs a key. The stub does keyword
matching, not language understanding. It is worse than the real thing, which
is the honest direction for a stand in to be wrong in.

It also un-hides the PLACEHOLDER scheme, which the matcher withholds by
design. Every value in that card is fake and says so.
"""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

import ask_handler  # noqa: E402
import llm  # noqa: E402

PORT = 8000

RULES = [
    ("area_type", "rural", (r"गाँव", r"गांव", r"village", r"रूरल")),
    ("area_type", "urban", (r"शहर", r"city", r"town", r"नगर")),
    ("has_existing_unit", False, (r"अभी.{0,15}नहीं", r"कोई इकाई नहीं", r"no business",
                                  r"not started", r"शुरू करना चाहत", r"want to start")),
    ("has_existing_unit", True, (r"पहले से", r"already run", r"i run", r"चल रही")),
    ("has_udyam_registration", True, (r"उद्यम", r"udyam")),
    ("caste_category", "sc", (r"\bsc\b", r"अनुसूचित जाति")),
    ("caste_category", "st", (r"\bst\b", r"अनुसूचित जनजाति")),
    ("caste_category", "obc", (r"\bobc\b", r"ओबीसी", r"पिछड़ा")),
    ("caste_category", "general", (r"\bgeneral\b", r"सामान्य")),
    ("gender", "female", (r"चाहती", r"बनाती", r"करती", r"रहती", r"महिला", r"\bwoman\b")),
    ("gender", "male", (r"चाहता", r"बनाता", r"करता", r"रहता", r"पुरुष", r"\bman\b")),
    ("state", "Madhya Pradesh", (r"मध्य प्रदेश", r"madhya pradesh", r"\bmp\b")),
    ("sector", "manufacturing", (r"दोना", r"पत्तल", r"leaf plate", r"सिलाई",
                                 r"tailor", r"बनात", r"making", r"manufactur")),
    ("sector", "trading", (r"दुकान", r"shop", r"बेचत", r"resell")),
]

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def fake_extract(text: str) -> dict:
    """Keyword matching. Deliberately not clever."""
    low = text.lower().translate(DEVANAGARI_DIGITS)
    profile: dict = {}

    for field, value, patterns in RULES:
        if field in profile:
            continue
        if any(re.search(p, low) for p in patterns):
            profile[field] = value

    age = re.search(r"\b(1[4-9]|[2-9][0-9])\b", low)
    if age:
        profile["age"] = int(age.group(1))

    return profile


def fake_cards(payload: dict) -> dict:
    """Assemble cards straight from the matcher's output. No invention:
    every string here came out of the scheme file."""
    hi = payload.get("language") == "hi"
    cards = []
    for s in payload.get("schemes", []):
        met = "; ".join(c for c in s.get("criteria_met") or [] if c)
        pending = "; ".join(c for c in s.get("still_to_confirm") or [] if c)
        why = met or (f"अभी जाँचना बाकी: {pending}" if hi else f"Still to confirm: {pending}")
        cards.append({
            "scheme_id": s["scheme_id"],
            "name": s.get("name"),
            "what_you_get": s.get("what_you_get"),
            "why_you_may_qualify": why,
            "documents": [d for d in s.get("documents") or [] if d],
            "next_step": " ".join(filter(None, [
                (s.get("next_step") or {}).get("office"),
                (s.get("next_step") or {}).get("what_to_carry"),
            ])),
        })

    n = len(cards)
    if hi:
        summary = f"आपने जो बताया, उसके आधार पर {n} योजना मिली है।" if n else "कोई योजना नहीं मिली।"
        closing = "कार्यालय में पुष्टि ज़रूर करें।"
    else:
        summary = f"Based on what you told us, we found {n} scheme(s)." if n else "We found nothing."
        closing = "Please confirm at the office."

    return {"summary": summary, "cards": cards, "closing": closing}


def stub_complete(system: str, messages) -> dict:
    """Stands in for llm.complete. Routes on which prompt it was given."""
    if "convert what a person says" in system:
        text = " ".join(m.get("text", "") for m in messages if m.get("role") == "user")
        return {"profile": fake_extract(text)}
    if "short, plain explanations" in system:
        return fake_cards(json.loads(messages[-1]["text"]))
    return {}


def load_demo_schemes() -> list[dict]:
    """The repo corpus, unmodified.

    Placeholder schemes stay hidden, exactly as in production. Now that a
    real transcribed scheme exists there is no reason to un-hide fabricated
    content, and every good reason not to.
    """
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "schemes").glob("*.json"))
    ]


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")

        result = ask_handler.handler({"body": body, "httpMethod": "POST"})

        self.send_response(result["statusCode"])
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(result["body"].encode("utf-8"))

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {fmt % args}\n")


if __name__ == "__main__":
    llm.complete = stub_complete
    ask_handler.load_schemes = load_demo_schemes
    ask_handler.COUNTER_TABLE = ""

    print("=" * 66)
    print("  DEMO HARNESS. The model is a keyword stub, not a language model.")
    print("  Scheme content is the real corpus; placeholders stay hidden.")
    print("  Matcher, validator and interview logic are the real ones.")
    print("=" * 66)
    print(f"  listening on http://localhost:{PORT}/ask")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
