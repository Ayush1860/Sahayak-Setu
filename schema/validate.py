"""Validate every file in /schemes/ against scheme.schema.json.

Fails on schema violations, on a missing or stale last_verified, and on
internal inconsistencies the JSON Schema cannot express (filename vs
scheme_id, duplicate criterion ids, source pages that are cited by a field
but absent from source_pages).

Usage:
    python schema/validate.py
    python schema/validate.py --max-age 90
    python schema/validate.py --no-placeholders   # fail if any PLACEHOLDER file remains
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    sys.exit("jsonschema is not installed. Run: pip install -r schema/requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "scheme.schema.json"
SCHEMES_DIR = ROOT / "schemes"
DEFAULT_MAX_AGE_DAYS = 180


def parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def cited_pages(scheme: dict) -> list[tuple[str, int]]:
    """Every source_page referenced anywhere in the record, with where it came from."""
    found: list[tuple[str, int]] = []

    def take(where: str, holder: object) -> None:
        if isinstance(holder, dict) and isinstance(holder.get("source_page"), int):
            found.append((where, holder["source_page"]))

    take("what_you_get", scheme.get("what_you_get"))
    take("next_physical_step", scheme.get("next_physical_step"))
    for i, step in enumerate(scheme.get("how_to_apply") or []):
        take(f"how_to_apply[{i}]", step)
    for i, doc in enumerate(scheme.get("documents_required") or []):
        take(f"documents_required[{i}]", doc)
    for crit in (scheme.get("eligibility") or {}).get("criteria") or []:
        take(f"criterion {crit.get('criterion_id', '?')}", crit)
    return found


def check_consistency(path: Path, scheme: dict, today: dt.date, max_age: int) -> tuple[list[str], list[str]]:
    """Checks that sit outside the JSON Schema. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    placeholder = bool(scheme.get("PLACEHOLDER"))

    if scheme.get("scheme_id") != path.stem:
        errors.append(f"scheme_id {scheme.get('scheme_id')!r} does not match filename {path.stem!r}")

    criteria = (scheme.get("eligibility") or {}).get("criteria") or []
    seen: set[str] = set()
    for crit in criteria:
        cid = crit.get("criterion_id")
        if cid in seen:
            errors.append(f"duplicate criterion_id {cid!r}")
        seen.add(cid)
        if crit.get("test") == "range":
            lo, hi = crit.get("min"), crit.get("max")
            if lo is not None and hi is not None and lo > hi:
                errors.append(f"criterion {cid!r}: min {lo} is greater than max {hi}")

    declared = set(scheme.get("source_pages") or [])
    for where, page in cited_pages(scheme):
        if page not in declared:
            errors.append(f"{where} cites page {page}, which is not listed in source_pages")

    verified = scheme.get("last_verified") or {}
    date = parse_date(verified.get("date", ""))
    if date is None:
        errors.append("last_verified.date is missing or not an ISO date")
    elif date > today:
        errors.append(f"last_verified.date {date} is in the future")
    elif placeholder:
        warnings.append("PLACEHOLDER file: staleness check skipped, the date is not real")
    else:
        age = (today - date).days
        if age > max_age:
            errors.append(f"last_verified.date {date} is {age} days old, limit is {max_age}")

    if placeholder:
        warnings.append("PLACEHOLDER is true: every value in this file is fake and must be hand verified before use")

    if not any(u.get("is_primary") for u in scheme.get("source_urls") or []):
        warnings.append("no source_url is marked is_primary")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the scheme corpus.")
    ap.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE_DAYS,
                    help=f"maximum age of last_verified in days (default {DEFAULT_MAX_AGE_DAYS})")
    ap.add_argument("--no-placeholders", action="store_true",
                    help="treat PLACEHOLDER files as errors")
    args = ap.parse_args()

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    today = dt.date.today()

    paths = sorted(SCHEMES_DIR.glob("*.json"))
    if not paths:
        print(f"No scheme files found in {SCHEMES_DIR}")
        return 0

    total_errors = 0
    total_warnings = 0

    for path in paths:
        errors: list[str] = []
        warnings: list[str] = []
        try:
            scheme = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"not valid JSON: {exc}")
            scheme = None

        if scheme is not None:
            for err in sorted(validator.iter_errors(scheme), key=lambda e: list(e.path)):
                where = "/".join(str(p) for p in err.path) or "(root)"
                errors.append(f"{where}: {err.message}")
            more_errors, warnings = check_consistency(path, scheme, today, args.max_age)
            errors.extend(more_errors)
            if args.no_placeholders and scheme.get("PLACEHOLDER"):
                errors.append("PLACEHOLDER is true and --no-placeholders was given")

        status = "FAIL" if errors else ("WARN" if warnings else "OK")
        print(f"[{status}] {path.name}")
        for err in errors:
            print(f"    error: {err}")
        for warn in warnings:
            print(f"    warn:  {warn}")

        total_errors += len(errors)
        total_warnings += len(warnings)

    print(f"\n{len(paths)} file(s), {total_errors} error(s), {total_warnings} warning(s)")
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
