"""Getting strict JSON out of a model that was asked for strict JSON.

Providers with a JSON mode still occasionally wrap output in fences or add a
sentence of preamble. This module is the one place that deals with it.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class ExtractionError(RuntimeError):
    """The model returned something that is not a usable JSON object."""


def strip_fences(raw: str) -> str:
    match = _FENCE.match(raw)
    return match.group(1) if match else raw.strip()


def parse_json_object(raw: str) -> dict[str, Any]:
    text = strip_fences(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ExtractionError(f"no JSON object in model output: {raw[:200]!r}")
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"model output is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ExtractionError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed
