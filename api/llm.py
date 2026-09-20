"""The only file that talks to a language model.

One function, complete(system, messages) -> dict. Two implementations behind
it. Which one runs is an environment variable, so moving between providers is
a config change and no application code moves.

This exists because Bedrock model invocation was blocked account-wide on a
new AWS account during the build. The AWS architecture did not change: the
handler, the corpus in S3, the counters in DynamoDB and the deploy are all
the same. Only the language layer moved.

What must stay true whichever provider is selected:

    The model converts language. It never decides eligibility.
    Its output is parsed to JSON here, then re-validated by the caller.
    A provider failure returns an empty dict, never a guess.
"""

from __future__ import annotations

import json
import os
from typing import Any, Sequence

from jsonio import ExtractionError, parse_json_object

PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()

GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "2000"))

_groq_client = None
_bedrock_client = None


class LLMError(RuntimeError):
    """The provider could not be reached or returned nothing usable."""


# --------------------------------------------------------------------- Groq

def _groq():
    global _groq_client
    if _groq_client is None:
        try:
            from groq import Groq
        except ImportError as exc:
            raise LLMError("groq is not installed. pip install groq") from exc
        if not GROQ_API_KEY:
            raise LLMError("GROQ_API_KEY is not set")
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _complete_groq(system: str, messages: Sequence[dict[str, str]]) -> dict[str, Any]:
    payload = [{"role": "system", "content": system}]
    for turn in messages:
        role = turn.get("role")
        text = turn.get("text") or turn.get("content")
        if text and role in ("user", "assistant"):
            payload.append({"role": role, "content": text})

    response = _groq().chat.completions.create(
        model=GROQ_MODEL,
        messages=payload,
        # Guaranteed JSON. Cheaper and more reliable than asking nicely.
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=MAX_TOKENS,
    )
    return parse_json_object(response.choices[0].message.content or "")


# ------------------------------------------------------------------ Bedrock

def _bedrock():
    global _bedrock_client
    if _bedrock_client is None:
        import boto3

        _bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _bedrock_client


def _complete_bedrock(system: str, messages: Sequence[dict[str, str]]) -> dict[str, Any]:
    payload = [
        {"role": t["role"], "content": [{"text": t.get("text") or t.get("content") or ""}]}
        for t in messages
        if t.get("role") in ("user", "assistant") and (t.get("text") or t.get("content"))
    ]
    response = _bedrock().converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": system}],
        messages=payload,
        inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0},
    )
    return parse_json_object(response["output"]["message"]["content"][0]["text"])


PROVIDERS = {
    "groq": _complete_groq,
    "bedrock": _complete_bedrock,
}


def complete(system: str, messages: Sequence[dict[str, str]]) -> dict[str, Any]:
    """Send a system prompt and a conversation, get a JSON object back.

    Returns {} rather than raising when the provider fails or returns
    something unparseable. Every caller treats an empty result as "we learned
    nothing", which is always safe: the interview asks another question, or
    the validator returns the refusal. A guess would not be safe.
    """
    impl = PROVIDERS.get(PROVIDER)
    if impl is None:
        raise LLMError(f"unknown LLM_PROVIDER {PROVIDER!r}, expected one of {sorted(PROVIDERS)}")

    try:
        return impl(system, messages)
    except (ExtractionError, LLMError):
        return {}
    except Exception:
        # Network, auth, rate limit, provider outage. Same answer: we do not
        # know. Never let a provider failure become a fabricated result.
        return {}


def describe() -> dict[str, str]:
    """What is actually configured. Used by the handler for diagnostics."""
    return {
        "provider": PROVIDER,
        "model": GROQ_MODEL if PROVIDER == "groq" else BEDROCK_MODEL_ID,
    }
