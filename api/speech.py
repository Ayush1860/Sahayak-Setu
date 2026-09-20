"""Speech to text, so the person can talk instead of type.

This is the input a villager actually has. Typing Devanagari on a cheap
phone means a keyboard many people have never set up; speaking is what they
already do.

Two rules, both about the audio.

The key lives here, not in the browser. A browser calling Sarvam directly
would ship the subscription key inside the JavaScript bundle, where anyone
can read it and spend it.

The audio is never stored. It arrives, it is forwarded, the transcript comes
back, and the bytes go out of scope. Nothing is written to /tmp, to S3 or to
DynamoDB. A recording of someone describing their poverty is exactly the
kind of thing this project promised not to keep.

The transcript is treated as untrusted text, identical to something typed:
it goes to the extractor, which re-validates every field against fields.py.
A misheard word cannot become an eligibility decision.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any

ENDPOINT = os.environ.get("SARVAM_STT_URL", "https://api.sarvam.ai/speech-to-text")
API_KEY = os.environ.get("SARVAM_API_KEY", "")
MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v3")
TIMEOUT_SECONDS = int(os.environ.get("SARVAM_TIMEOUT", "25"))

# Sarvam's REST endpoint is for clips under 30 seconds. A cap here keeps a
# long upload from burning the Lambda's 30s budget and timing out the person.
MAX_AUDIO_BYTES = 8 * 1024 * 1024


class SpeechError(RuntimeError):
    """Transcription failed. The caller falls back to the keyboard."""


def _multipart(audio: bytes, filename: str, content_type: str,
               fields: dict[str, str]) -> tuple[bytes, str]:
    """Build a multipart/form-data body with the standard library only."""
    boundary = f"----sahayaksetu{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts: list[bytes] = []

    for name, value in fields.items():
        parts += [
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{name}"'.encode(),
            b"",
            value.encode("utf-8"),
        ]

    parts += [
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode(),
        f"Content-Type: {content_type}".encode(),
        b"",
        audio,
        f"--{boundary}--".encode(),
        b"",
    ]

    return crlf.join(parts), f"multipart/form-data; boundary={boundary}"


def transcribe(audio: bytes, content_type: str = "audio/webm") -> dict[str, Any]:
    """Return {"text": ..., "language": "hi"|"en"}.

    Raises SpeechError on any failure. The caller shows the keyboard rather
    than guessing at what was said.
    """
    if not API_KEY:
        raise SpeechError("SARVAM_API_KEY is not set")
    if not audio:
        raise SpeechError("no audio")
    if len(audio) > MAX_AUDIO_BYTES:
        raise SpeechError("audio is too long")

    extension = {"audio/webm": "webm", "audio/ogg": "ogg",
                 "audio/mp4": "m4a", "audio/wav": "wav"}.get(content_type, "webm")

    body, header = _multipart(
        audio, f"speech.{extension}", content_type,
        # unknown means Sarvam detects the language. The person should not
        # have to declare which language they are about to speak.
        {"model": MODEL, "language_code": "unknown"},
    )

    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": header, "api-subscription-key": API_KEY},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SpeechError(f"sarvam returned {exc.code}") from exc
    except Exception as exc:
        raise SpeechError(f"sarvam unreachable: {type(exc).__name__}") from exc

    text = (payload.get("transcript") or "").strip()
    if not text:
        raise SpeechError("empty transcript")

    # hi-IN -> hi. Anything we do not recognise falls back to script
    # detection in the extractor, which is the more reliable signal anyway.
    code = (payload.get("language_code") or "").split("-")[0].lower()
    return {"text": text, "language": code if code in ("hi", "en") else ""}
