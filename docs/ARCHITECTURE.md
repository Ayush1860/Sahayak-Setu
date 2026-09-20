# Architecture

## The shape of a request

```
POST /ask  { "conversation": [{"role": "user", "text": "..."}], "asked": [] }
```

`ask_handler.handler` runs five stages and owns no logic of its own.

| Stage | File | Model | What it does |
|---|---|---|---|
| 1 | `extractor.py` | yes | Conversation to a structured profile |
| 2 | `interview.py` | no | Decide the one next question, or stop |
| 3 | `matcher.py` | no | Evaluate the profile against every scheme |
| 4 | `explainer.py` | yes | Write the cards in Hindi or English |
| 5 | `validator.py` | no | Delete anything unsupported, or refuse |

The response is either a single question or a validated answer.

## Why eligibility is code

A model asked "does this person qualify?" will answer. It will answer
confidently when the rules are ambiguous, when the profile is half known, and
when it has never seen the scheme. Those answers are unauditable and vary
between runs. When the subject is whether someone gets a subsidy they are
entitled to, that is not an acceptable failure mode.

So the decision is a loop over structured criteria.

### Three-valued logic

Each criterion evaluates to `PASS`, `FAIL` or `UNKNOWN`.

`UNKNOWN` is the one that matters. A field the profile does not carry cannot
rule anyone in or out, so it becomes a question rather than a verdict. This
is a property of the data model, not a matcher convention, which is why a
half-finished interview cannot silently exclude anyone.

```
any FAIL          -> excluded, naming every criterion that failed
else any UNKNOWN  -> likely, listing what still has to be confirmed
else              -> matched
```

`matched` still reads "likely eligible, confirm at the office".

### Criteria are uniform

A fixed shape (`age_min`, `castes_allowed`, ...) forces the matcher into an
`if` chain that grows with every scheme. A uniform list of criterion objects
means one loop over one dispatch table, and a new rule type is one small
function.

```json
{
  "criterion_id": "age_range",
  "field": "age",
  "test": "range",
  "min": 18, "max": 45,
  "label_en": "Age 18 to 45",
  "source_page": 12
}
```

Five test types: `range`, `one_of`, `none_of`, `boolean`, `manual`.

`manual` is a first-class type for conditions code cannot decide. It always
evaluates `UNKNOWN` and always surfaces as something to confirm at the
office. Without it, unstructurable conditions live in a notes field, get
ignored by the matcher, and quietly overstate eligibility.

### The closed field vocabulary

`fields.py` holds the profile fields, and a test asserts it matches the
`profile_field` enum in `schema/scheme.schema.json`. If the extractor emits
`caste` and a scheme reads `caste_category`, every criterion using it goes
`UNKNOWN` forever: schemes silently stop matching and the app looks like it
is working. The closed enum turns that into a CI failure.

The same applies to values. `VOCABULARIES` in `fields.py` must match the
`values` arrays in the scheme files, lowercase on both sides.

## Why the validator exists

The explainer is given only the schemes the matcher chose, and only the
fields it may speak about, assembled one at a time rather than handed whole
scheme records. It still cannot be trusted, so:

- Every `scheme_id` in its output must be in the matched set. Otherwise the
  card is deleted.
- Every URL in free text must be in that scheme's `source_urls`. Otherwise
  the URL is stripped.
- Citations shown to the user are read from the corpus, never copied from the
  model output.
- A scheme with no verified source URL is dropped even if the matcher chose
  it. No citation, no answer.
- If nothing survives, the response is the refusal.

`test_validator.py` includes a fixture where the model invents two schemes
and two URLs. All four are deleted.

## The provider interface

`llm.py` is the only file that talks to a model. One function,
`complete(system, messages) -> dict`, with Groq and Bedrock behind it,
selected by `LLM_PROVIDER`.

This exists because Bedrock model invocation was blocked account-wide on a
new AWS account during the build, for every provider including Amazon's own
Nova. The AWS architecture did not change; only where the sentences are
generated moved.

A provider failure returns `{}`, never a guess. An outage degrades to another
interview question, or to the refusal.

## AWS specifics worth knowing

**Inference profiles.** Most current Claude models on Bedrock cannot be
invoked by their bare model id. They need a cross-region inference profile,
prefixed `apac.` or `global.`. Calling the bare id returns
`ValidationException: ... on-demand throughput isn't supported`, which reads
like a quota problem and is not. `scratch/test_bedrock.py --list` discovers
valid ids from your own account rather than hardcoding one.

**The IAM region wildcard is deliberate.** A `global.` profile routes to
whichever region has capacity and needs invoke permission on the underlying
foundation model *there*. Pinning the region makes global profiles fail
intermittently.

**Model access is per region and may need an agreement.** Anthropic models
require a one-time use-case submission per account.
`aws bedrock get-foundation-model-availability --model-id <id> --region <r>`
distinguishes "not entitled", "not in this region" and "agreement unsigned",
all of which surface as the same opaque error at invoke time.

**`/tmp` persists across warm invocations.** The scheme corpus is downloaded
from S3 once per container, not once per request.

**Least privilege in `template.yaml`.** S3 `GetObject`/`ListBucket` on one
bucket, Bedrock invoke only, DynamoDB `UpdateItem` only. Not the blanket
`FullAccess` policies.

## Deploying

```bash
sam build
sam deploy --guided
```

`--guided` asks for:

- **Stack name** and **region**. Use `ap-south-1`.
- **LlmProvider** — `groq` or `bedrock`.
- **GroqApiKey** — `NoEcho`, so it will not appear in stack outputs.
- **GroqModel** — verify against the provider's current model list first;
  model ids are deprecated on a rolling basis.
- **BedrockModelId** — an inference profile id, not a bare model id.
- **SchemesBucketName** — must be globally unique.
- **AllowedOrigin** — the Amplify URL. Do not leave it as `*` in production.
- **Allow IAM role creation** — yes, it needs to create the execution role.
- **Save to samconfig.toml** — yes. That file is gitignored, because with
  `GroqApiKey` among the parameters it would otherwise carry your key into
  version control.

Then upload the corpus and point the frontend at the API:

```bash
aws s3 sync schemes/ s3://<bucket>/schemes/ --exclude "*" --include "*.json"
```

```bash
curl -X POST "$API_URL/ask" -H "Content-Type: application/json" \
  -d '{"conversation":[{"role":"user","text":"I make leaf plates"}],"asked":[]}'
```

## Testing

128 tests, no AWS calls. Two are structural rather than behavioural:

- `test_matcher_imports_nothing_that_can_reach_a_network` parses `matcher.py`
  and fails if `boto3`, `requests`, `urllib` or `extractor` appear among its
  imports. It is what makes "eligibility is decided by code" checkable rather
  than a claim in a README.
- `test_counters_never_receive_anything_about_a_person` asserts no age,
  income, caste or gender value reaches DynamoDB.
