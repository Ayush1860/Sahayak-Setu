"""Keep unverified placeholders away from users.

A scheme file can be partly transcribed: clause 7.1.1 read off the page, the
application procedure not yet read. Those gaps are written into the file as
markers so the transcriber can see what is outstanding.

A user must never see them. "NOT YET VERIFIED" on a card is worse than an
absent field: it looks like a system error and it teaches the person that the
answer is unreliable in general, when in fact the part they were shown is
sound.

So the markers are stripped at the point the data leaves the corpus. Nothing
here edits a scheme file; the file keeps its markers for whoever finishes it.
"""

from __future__ import annotations

import re
from typing import Any

MARKERS = (
    "NOT YET VERIFIED",
    "VERIFY THIS",
    "सत्यापित करें",
    "अभी सत्यापित नहीं",
)

_SPLIT = re.compile(r"\s+-\s+")


def _has_marker(text: str) -> bool:
    upper = text.upper()
    return any(m.upper() in upper for m in MARKERS)


def visible(text: Any) -> str | None:
    """The part of this string a user may see, or None if there is none.

    A marker in the first segment means the whole value is a placeholder, so
    nothing is shown. A marker in a later segment is an annotation appended
    to real content, so only that segment is removed.

        "NOT YET VERIFIED - not stated on page 13"      -> None
        "District Trade and Industry Centre - VERIFY THIS"
                                       -> "District Trade and Industry Centre"
    """
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None
    if not _has_marker(text):
        return text

    parts = _SPLIT.split(text)
    if _has_marker(parts[0]):
        return None

    kept = [p for p in parts if not _has_marker(p)]
    return " - ".join(kept).strip() or None


def visible_list(items: Any) -> list[str]:
    """Every entry that survives. An all-placeholder list becomes empty."""
    if not isinstance(items, list):
        return []
    return [v for v in (visible(i) for i in items) if v]
