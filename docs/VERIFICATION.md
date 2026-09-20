# Verification

How each scheme in `/schemes/` was checked, and by whom.

## The standard

Every value in the corpus was read off a primary source document by a person.
Not summarised by a model, not copied from an aggregator site, not inferred
from a news article.

**OCR output was never trusted unreviewed.** The pipeline in `/pipeline/`
exists to save typing, not to produce facts. It emits drafts with
`"verified": false` on every extracted value. That flag is removed by a human,
one value at a time, with the source page open.

This matters because the failure is silent and expensive. A misread subsidy
percentage does not throw an error. It sends someone on a bus to a district
office, with documents they took a day off to collect, for a benefit that
does not apply to them. They will not come back a second time.

## Current status, as of 2026-09-20

**No real scheme has been verified yet. The corpus is not ready for use.**

| File | Status | Verified by | Notes |
|---|---|---|---|
| `example_placeholder_scheme.json` | `PLACEHOLDER: true` | nobody | Every value fabricated. Withheld from results by the matcher. |

The placeholder exists so the schema, matcher and frontend can be exercised
end to end. Its values are deliberately obvious: age bounds of 11 to 99,
categories named `PLACEHOLDER_A` and `PLACEHOLDER_B`, a URL on
`example.invalid`. Nothing in it could be mistaken for real advice, and
`api/matcher.py` withholds any file carrying the flag.

Until a real scheme is added, the app refuses every query. That is the
correct behaviour, not a bug.

## What a verified entry looks like

When a scheme is verified, add a row here with:

- the file
- the exact source document, including its date or version
- the page numbers each section was read from
- who checked it and when
- anything ambiguous in the source, and how it was resolved

Ambiguity is worth recording. If a policy says "units in rural areas" without
defining rural, note that, and use a `manual` criterion rather than guessing
a definition.

## Re-verification

`schema/validate.py` fails when `last_verified.date` is more than 180 days
old. Government schemes change without announcement; budget cycles revise
subsidy rates; portals move.

An entry going stale is not a formality. Re-read the source and update the
date, or remove the scheme. Do not extend the window because CI is red.

## Known limitations of the source material

The MP MSME Development Policy 2025 is a 56-page, 59 MB PDF exported from
CorelDRAW with zero extractable text. Every page is an image. Expect OCR to
struggle in three specific places:

- **Multi-column layouts.** Text order across columns is frequently wrong,
  which can attach a condition to the wrong scheme.
- **Subsidy rate tables.** Row and column headers get separated from their
  cells. A percentage may end up next to the wrong category.
- **Devanagari and English on the same page.** Mixed-script lines are where
  character-level errors cluster, and a misread digit is invisible.

Every one of those failures produces output that looks correct. That is why
the flag comes off by hand.
