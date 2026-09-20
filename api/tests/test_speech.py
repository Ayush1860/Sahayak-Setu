"""Speech to text tests. Sarvam is never contacted.

The things that matter here are not about accuracy. They are about what
happens to a recording of someone's voice, and what happens when the
transcription is wrong or missing.
"""

from __future__ import annotations

import ast
import base64
import json
from pathlib import Path

import pytest

import ask_handler
import speech


# ------------------------------------------------------------ the audio

def test_the_audio_is_never_written_anywhere():
    """No open(), no S3, no DynamoDB. The bytes are forwarded and then go out
    of scope.

    Reads the parsed code rather than the text, so the module can go on
    explaining in its docstring that it does not write to /tmp without the
    word /tmp failing its own test.
    """
    tree = ast.parse(Path(speech.__file__).read_text(encoding="utf-8"))

    imported: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)

    assert "open" not in called, "speech.py opens a file"
    assert not (imported & {"boto3", "botocore", "shutil", "tempfile", "pickle"})
    assert not (called & {"put_object", "upload_fileobj", "write_bytes",
                          "write_text", "update_item", "mkdir"})


def test_the_key_is_read_from_the_environment_not_hardcoded():
    source = Path(speech.__file__).read_text(encoding="utf-8")
    assert 'os.environ.get("SARVAM_API_KEY"' in source


def test_no_key_means_a_clear_error_not_a_silent_failure(monkeypatch):
    monkeypatch.setattr(speech, "API_KEY", "")
    with pytest.raises(speech.SpeechError):
        speech.transcribe(b"audio")


def test_empty_audio_is_rejected(monkeypatch):
    monkeypatch.setattr(speech, "API_KEY", "k")
    with pytest.raises(speech.SpeechError):
        speech.transcribe(b"")


def test_oversized_audio_is_rejected_before_it_is_sent(monkeypatch):
    monkeypatch.setattr(speech, "API_KEY", "k")
    with pytest.raises(speech.SpeechError):
        speech.transcribe(b"x" * (speech.MAX_AUDIO_BYTES + 1))


# --------------------------------------------------- the multipart body

def test_the_body_carries_the_file_and_the_model():
    body, header = speech._multipart(
        b"AUDIOBYTES", "speech.webm", "audio/webm",
        {"model": "saaras:v3", "language_code": "unknown"},
    )
    assert "multipart/form-data; boundary=" in header
    assert b'name="file"; filename="speech.webm"' in body
    assert b"AUDIOBYTES" in body
    assert b"saaras:v3" in body
    # The language is not declared for the person. Sarvam detects it.
    assert b"unknown" in body


def test_the_boundary_is_not_reused_between_requests():
    _, first = speech._multipart(b"a", "f", "audio/webm", {})
    _, second = speech._multipart(b"a", "f", "audio/webm", {})
    assert first != second


# ------------------------------------------------------ the transcript

class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def stub_urlopen(monkeypatch, payload):
    monkeypatch.setattr(speech, "API_KEY", "k")
    monkeypatch.setattr(speech.urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResponse(payload))


def test_a_hindi_transcript_comes_back_with_its_language(monkeypatch):
    stub_urlopen(monkeypatch, {"transcript": "मैं दोना पत्तल बनाता हूँ",
                               "language_code": "hi-IN"})
    out = speech.transcribe(b"audio")
    assert out["text"] == "मैं दोना पत्तल बनाता हूँ"
    assert out["language"] == "hi"


def test_an_unfamiliar_language_code_is_left_to_script_detection(monkeypatch):
    stub_urlopen(monkeypatch, {"transcript": "text", "language_code": "ta-IN"})
    assert speech.transcribe(b"audio")["language"] == ""


def test_an_empty_transcript_is_an_error_not_an_empty_answer(monkeypatch):
    stub_urlopen(monkeypatch, {"transcript": "   ", "language_code": "hi-IN"})
    with pytest.raises(speech.SpeechError):
        speech.transcribe(b"audio")


# ------------------------------------------------------- the endpoint

def call_transcribe(body):
    return ask_handler.handler(
        {"body": json.dumps(body), "httpMethod": "POST", "rawPath": "/transcribe"}
    )


def test_bad_base64_is_a_400():
    assert call_transcribe({"audio": "not base64!!"})["statusCode"] == 400


def test_a_failure_returns_empty_text_so_the_person_can_type(monkeypatch):
    """Never invent what someone might have said. Show the keyboard."""
    monkeypatch.setattr(ask_handler, "COUNTER_TABLE", "")
    monkeypatch.setattr(speech, "API_KEY", "")

    r = call_transcribe({"audio": base64.b64encode(b"audio").decode()})
    body = json.loads(r["body"])
    assert r["statusCode"] == 200
    assert body["text"] == ""


def test_a_transcript_is_returned_to_the_browser(monkeypatch):
    monkeypatch.setattr(ask_handler, "COUNTER_TABLE", "")
    stub_urlopen(monkeypatch, {"transcript": "नमस्ते", "language_code": "hi-IN"})

    r = call_transcribe({"audio": base64.b64encode(b"audio").decode()})
    body = json.loads(r["body"])
    assert body["type"] == "transcript"
    assert body["text"] == "नमस्ते"


def test_the_key_never_reaches_the_browser(monkeypatch):
    monkeypatch.setattr(ask_handler, "COUNTER_TABLE", "")
    monkeypatch.setattr(speech, "API_KEY", "sarvam_secret_key_value")
    stub_urlopen(monkeypatch, {"transcript": "x", "language_code": "hi-IN"})
    monkeypatch.setattr(speech, "API_KEY", "sarvam_secret_key_value")

    r = call_transcribe({"audio": base64.b64encode(b"audio").decode()})
    assert "sarvam_secret_key_value" not in r["body"]


def test_counters_record_only_whether_it_worked(monkeypatch):
    writes = []
    monkeypatch.setattr(ask_handler, "COUNTER_TABLE", "counters")
    monkeypatch.setattr(ask_handler, "dynamo",
                        lambda: type("D", (), {"update_item": lambda self, **kw: writes.append(kw)})())
    stub_urlopen(monkeypatch, {"transcript": "मैं गाँव में रहता हूँ", "language_code": "hi-IN"})

    call_transcribe({"audio": base64.b64encode(b"audio").decode()})

    written = json.dumps(writes, ensure_ascii=False)
    assert "गाँव" not in written, "transcript text reached DynamoDB"
    assert "speech_ok" in written
