"""Lambda entry point. Wires the pieces together and owns none of the logic.

    extractor  -> what did this person tell us
    interview  -> is one more question worth asking
    matcher    -> who qualifies for what          (no model)
    explainer  -> say it in their language
    validator  -> delete anything unsupported     (no model)

Privacy: the profile exists for the duration of one request and is never
written anywhere. DynamoDB receives counters only. No message text, no
profile, no caste, no gender, no income. If you are changing this file,
that is the line not to cross.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import boto3

import explainer
import extractor
import interview
import validator
from matcher import match

REGION = os.environ.get("AWS_REGION", "ap-south-1")
SCHEMES_BUCKET = os.environ.get("SCHEMES_BUCKET", "")
SCHEMES_PREFIX = os.environ.get("SCHEMES_PREFIX", "schemes/")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "")
COUNTER_TABLE = os.environ.get("COUNTER_TABLE", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

# Lambda keeps /tmp between warm invocations, so the corpus is fetched from S3
# once per container rather than once per request.
CACHE_DIR = Path("/tmp/schemes")
_schemes_cache: list[dict] | None = None

_bedrock = None
_s3 = None
_dynamo = None


def bedrock():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    return _bedrock


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=REGION)
    return _s3


def dynamo():
    global _dynamo
    if _dynamo is None:
        _dynamo = boto3.client("dynamodb", region_name=REGION)
    return _dynamo


def load_schemes() -> list[dict]:
    """Corpus from S3, cached in /tmp across warm invocations."""
    global _schemes_cache
    if _schemes_cache is not None:
        return _schemes_cache

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    schemes: list[dict] = []

    if not SCHEMES_BUCKET:
        # Local development: read the repo copy.
        local = Path(__file__).resolve().parent.parent / "schemes"
        for path in sorted(local.glob("*.json")):
            schemes.append(json.loads(path.read_text(encoding="utf-8")))
        _schemes_cache = schemes
        return schemes

    paginator = s3().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=SCHEMES_BUCKET, Prefix=SCHEMES_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            cached = CACHE_DIR / Path(key).name
            if not cached.exists():
                s3().download_file(SCHEMES_BUCKET, key, str(cached))
            schemes.append(json.loads(cached.read_text(encoding="utf-8")))

    _schemes_cache = schemes
    return schemes


def count(event_name: str, scheme_ids: list[str] | None = None) -> None:
    """Anonymous counters only. Never called with anything about a person."""
    if not COUNTER_TABLE:
        return
    try:
        day = time.strftime("%Y-%m-%d")
        dynamo().update_item(
            TableName=COUNTER_TABLE,
            Key={"pk": {"S": f"count#{day}"}, "sk": {"S": event_name}},
            UpdateExpression="ADD #n :one",
            ExpressionAttributeNames={"#n": "total"},
            ExpressionAttributeValues={":one": {"N": "1"}},
        )
        for scheme_id in scheme_ids or []:
            dynamo().update_item(
                TableName=COUNTER_TABLE,
                Key={"pk": {"S": f"scheme#{day}"}, "sk": {"S": scheme_id}},
                UpdateExpression="ADD #n :one",
                ExpressionAttributeNames={"#n": "total"},
                ExpressionAttributeValues={":one": {"N": "1"}},
            )
    except Exception:
        # A counter must never break a person's answer.
        pass


def respond(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    if (event.get("requestContext", {}).get("http", {}).get("method")
            or event.get("httpMethod")) == "OPTIONS":
        return respond(200, {})

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return respond(400, {"error": "body is not JSON"})

    conversation = body.get("conversation") or []
    asked = body.get("asked") or []
    if not isinstance(conversation, list) or not conversation:
        return respond(400, {"error": "conversation is required"})

    schemes = load_schemes()

    extracted = extractor.extract(conversation, bedrock(), MODEL_ID)
    profile, language = extracted["profile"], extracted["language"]

    question = interview.next_question(profile, schemes, asked=asked, language=language)
    if question is not None:
        count("question_asked")
        return respond(200, {
            "type": "question",
            "question": question["text"],
            "field": question["field"],
            "asked": asked + [question["field"]],
            "language": language,
        })

    results = match(profile, schemes, language)
    shortlist = results["matched"] + results["likely"]

    if not shortlist:
        count("refused")
        answer = validator.validate({}, [], schemes, language)
    else:
        draft = explainer.explain(shortlist, schemes, bedrock(), MODEL_ID, language)
        answer = validator.validate(draft, shortlist, schemes, language)
        count("refused" if answer["refused"] else "answered",
              [c["scheme_id"] for c in answer["cards"]])

    answer["type"] = "answer"
    answer["language"] = language
    answer["request_id"] = str(uuid.uuid4())
    return respond(200, answer)
