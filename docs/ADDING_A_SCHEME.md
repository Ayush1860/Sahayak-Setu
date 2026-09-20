# Adding a scheme

Written for someone forking this for another state. Nothing here requires
touching application code.

## Before you start

You need the source document. Not a news article about the scheme, not a
summary on an aggregator site, not a chatbot's description. The government
order, the policy PDF, or the official scheme page.

If you cannot find a primary source, **do not add the scheme.** A card with
no verifiable citation is deleted by the validator anyway, so it would never
reach a user. More importantly, wrong scheme content sends someone on a bus
to an office for a benefit that does not exist.

## 1. Create the file

One JSON file per scheme in `/schemes/`. The filename without `.json` must
equal `scheme_id`, lowercase with underscores.

Start from `schemes/example_placeholder_scheme.json`. Keep
`"PLACEHOLDER": true` while you work: the matcher withholds placeholder
schemes from results, so a half-finished file cannot reach a user. Remove the
flag only when every value has been checked against the source.

## 2. Write the eligibility criteria

This is the part the matcher reads. Everything else is text.

```json
{
  "criterion_id": "age_range",
  "field": "age",
  "test": "range",
  "min": 18,
  "max": 45,
  "label_en": "Age 18 to 45",
  "label_hi": "उम्र 18 से 45",
  "source_page": 12
}
```

- `field` must come from the enum in `schema/scheme.schema.json`. If your
  scheme needs a field that does not exist, see "Adding a new field" below.
- `label_en` and `label_hi` state **what is required**, not what the person
  did. They are shown to the user as the reason a scheme matched, so write
  them as a plain phrase: "Age 18 to 45", not "applicant satisfies age
  criterion".
- `source_page` is the page of the source document where you read this rule.
  It must also appear in the scheme's `source_pages` array, and `validate.py`
  fails if it does not.

### The five tests

| test | Use for | Needs |
|---|---|---|
| `range` | Numeric bounds | `min` and/or `max` |
| `one_of` | Value must be in a set | `values` |
| `none_of` | Value must not be in a set | `values` |
| `boolean` | A yes/no fact | `expected` |
| `manual` | Code cannot decide this | nothing |

### When to use `manual`

Use it for any condition a structured test cannot express: "at the discretion
of the District Industries Centre", "subject to availability of funds",
"preference to units in notified backward blocks".

A `manual` criterion always evaluates `UNKNOWN`, so the scheme stays
"likely" and the condition appears in the list of things to confirm at the
office. That is the honest outcome.

**Do not** put such a condition only in `notes_en`. Notes are displayed but
never evaluated, so a note that would change who qualifies makes the app
overstate eligibility.

### Values must match the vocabulary

If a criterion says `"values": ["SC", "ST"]` but the extractor emits `sc`,
the criterion never passes and nobody is told why. Keep both lowercase.
`VOCABULARIES` in `api/fields.py` is the list.

## 3. Fill in the rest

`what_you_get` is the benefit in the user's words. Free text, transcribed
from the source. Never a number you calculated.

`next_physical_step` is the most useful field in the record. Which office,
and what to carry. Be specific: "District Industries Centre, Collectorate
compound" beats "the concerned department".

`source_urls` must be `https` and official. The validator only lets URLs from
this array reach a user.

`last_verified` is the date **a human** checked this record against the
source, and their name. `validate.py` fails if it is missing, in the future,
or more than 180 days old.

Every string field has an `_en` and `_hi` pair. Both are required. Write the
Hindi for someone with limited formal schooling: short sentences, common
words, no officialese.

## 4. Validate

```bash
python schema/validate.py
```

It checks the schema plus the things a schema cannot express: filename
against `scheme_id`, duplicate criterion ids, inverted ranges, pages cited
but not declared, and staleness.

```bash
python -m pytest -q
```

## 5. Remove the placeholder flag

Only when every value has been read off the source document by a person.
Then record what you did in `docs/VERIFICATION.md`.

Once no placeholder files remain, add `--no-placeholders` to the CI workflow
so an unverified file can never be merged.

## Adding a new field

If your state's schemes need something the vocabulary lacks, for example
years in the trade:

1. Add it to `$defs/profile_field` in `schema/scheme.schema.json`
2. Add it to `PROFILE_FIELDS` and `FIELD_TYPES` in `api/fields.py`, plus
   `VOCABULARIES` or `NUMERIC_BOUNDS` if it is constrained
3. Add a question for it in `api/interview.py`, in both languages
4. Mention it in `api/prompts/extractor_system.txt`, including what must
   **not** be inferred
5. Run the tests. `test_profile_fields_match_the_schema_enum` fails if you
   missed step 1 or 2

Deliberate friction. Adding a field silently is how schemes stop matching
with no error.

## What not to do

**Do not let a model write scheme content.** Not the subsidy percentage, not
the income ceiling, not the age bounds, not the office name. A model will
produce plausible, specific, wrong numbers, and there is no way to tell by
looking. Every value in `/schemes/` is a number a person read off a document.

**Do not trust OCR output.** `pipeline/` produces drafts with
`"verified": false`. That flag comes off by hand, per value.

**Do not add a scheme you cannot cite.** No citation, no answer.
