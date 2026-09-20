<img src="assets/logo.webp" alt="Sahayak Setu" width="360">

# Sahayak Setu

**An interview, not a search box.** A person describes their work in Hindi, by
speaking or tapping. Two or three short questions later they get the
government schemes they may be eligible for, each with the criterion they
meet, the page of the source document it came from, and which office to walk
into.

**Live:** https://main.d33gsnpqabzyco.amplifyapp.com

**Eligibility is decided by plain Python, never by a model.**

---

## The problem

Indian government schemes exist for people who do not know they exist. A man
making dona-pattal, leaf plates, at home in a village in Madhya Pradesh is
eligible for subsidised credit, capital subsidy and power-tariff concessions,
and pays full rates because nobody told him.

The source documents are hostile to access. For Example the MP MSME Development Policy
2025 is a 56-page, 59 MB PDF exported from CorelDRAW with **zero extractable
text**. Every page is an image: not searchable, not selectable, invisible to
a screen reader, useless to any software. It is in English, for a scheme
aimed at rural micro-enterprise.

A search box does not help someone who does not know the name of the thing
they are searching for. So the app asks.

---

## Three rules, enforced by code

### 1. Eligibility is decided by code

[`api/matcher.py`](api/matcher.py) reads structured eligibility blocks and
returns a verdict. It imports nothing that can reach a network, and
`test_matcher_imports_nothing_that_can_reach_a_network` parses the module's
own AST to prove it. A model converts language into a profile before it runs,
and writes the explanation after. It never decides who qualifies.

Every criterion evaluates to **PASS**, **FAIL** or **UNKNOWN**. UNKNOWN is the
one that matters: a field nobody has been asked about cannot rule anyone in or
out, so it becomes a question instead of a verdict.

```
any FAIL          -> excluded, naming the criterion that failed
else any UNKNOWN  -> likely, listing what still has to be confirmed
else              -> matched
```

The strongest verdict is **"likely eligible, confirm at the office"**. Nothing
here tells anyone they are entitled to anything, because only an officer with
the documents in hand can say that.

### 2. Every answer cites a verified source with a date

[`api/validator.py`](api/validator.py) runs after the model. Every scheme id
must be in the matched set; every URL must be in that scheme's `source_urls`.
Anything else is deleted. **Citations are attached from the corpus, never
copied from the model**, so a URL physically cannot reach a user unless a
human put it in a scheme file.

`test_hallucinated_schemes_are_deleted` feeds it a model output that invents
two schemes and two URLs. All four vanish.

### 3. Nothing computes a number nobody wrote down

The policy states a base rate of 40% *and* an additional 2.5% per year for
four years. Those do not obviously total 42.5%; read as instalments they may
total nearer 50%. The page does not say. So
[`api/rates.py`](api/rates.py) **selects** which lines apply and shows each in
the source's own words with its page number. It never adds them up, and a
test fails the build on any arithmetic operator in the file.

---

## How it works

```
  browser (React on Amplify Hosting)
        |  POST /ask        { conversation, answers, asked }
        |  POST /transcribe { audio }
        v
  API Gateway  ->  Lambda: api/ask_handler.py
        |
        |  1. speech.py     voice -> text            [Sarvam AI]
        |  2. extractor.py  language -> profile      [model]
        |  3. interview.py  one next question        [no model]
        |  4. matcher.py    who qualifies for what   [no model]
        |  5. explainer.py  profile -> Hindi cards   [model]
        |  6. validator.py  delete the unsupported   [no model]
        |
        +-- S3          verified scheme corpus, cached in /tmp
        +-- DynamoDB    anonymous counters only
        +-- llm.py      one interface, Groq or Bedrock, one variable
```

Two model calls per conversation, both for language only. Everything between
them is deterministic.

**The interview is taps, not typing.** Numbers are buckets ("1 to 10 lakh"),
vocabularies are buttons in plain language ("I make things", not
"manufacturing"), state is a dropdown, and "I do not know" is a real answer
that leaves the criterion UNKNOWN. A bucket is evaluated as an *interval*: one
entirely inside a criterion passes, entirely outside fails, and one straddling
the boundary is UNKNOWN rather than a guess.

Because tapped answers are data rather than something to re-extract, **the
interview keeps working when the model provider does not**, and a matched
scheme falls back to a card assembled from corpus text rather than becoming a
refusal.

Deliberately not used: OpenSearch (overkill for five documents, where matching
is deterministic rather than retrieval), Cognito (no accounts; asking a
villager to sign up defeats the purpose), Step Functions (two calls need no
orchestration).

---

## Privacy

- **The name never leaves the device.** It is not in any request, and the
  screen says so.
- **Audio is never stored.** Forwarded to Sarvam, transcribed, dropped. A test
  reads `speech.py`'s AST and fails on `open()`, `boto3`, `tempfile` or any
  write call.
- Caste category, gender and income are collected in-session and never
  persisted. The profile exists for the duration of one request.
- DynamoDB stores **counters only**: how many queries, matched versus refused,
  which schemes fired. A test asserts no age, income, caste or gender value
  can reach it, and the Lambda's IAM policy grants `UpdateItem` and nothing
  else, so a bug cannot turn the counter table into a data source.

---

## Running it

```bash
pip install -r schema/requirements.txt -r api/requirements.txt
python -m pytest -q          # 214 tests, no AWS calls
python schema/validate.py    # validate the scheme corpus
```

Click through the whole flow with **no model and no AWS account**:

```bash
python scratch/dev_server.py
```

```bash
cd web && npm install && npm run dev
```

The harness replaces the model with keyword matching. Matcher, validator and
interview are the real ones.

---

## Deploying

```bash
sam build && sam deploy --guided
```

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) covers what `--guided` asks, and
the AWS specifics that cost real time: Bedrock inference profiles, why the IAM
region wildcard is deliberate, and `get-foundation-model-availability` as the
diagnostic that separates three failures which look identical at invoke time.

---

## Disclaimer

**This is informational only. It is not legal, financial or official advice.**

Scheme content is transcribed from public government documents by hand and may
be out of date, incomplete or wrong. Rules change without notice. Nothing here
confirms that anyone is eligible for anything. Always confirm at the office
named on the card before acting.

The corpus currently holds one hand-transcribed scheme, clause 7.1.1 of the MP
MSME Development Policy 2025, with `verified: false` pending a second pass,
plus one placeholder that the matcher withholds by design. Five fields are
marked unverified and are hidden from users rather than shown as gaps. See
[`docs/VERIFICATION.md`](docs/VERIFICATION.md), which records what was checked
and what was not.

**OCR output was never trusted unreviewed.** Every value in `/schemes/` was
read off the source document by a person.

---

## Docs

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — why eligibility is code, and the AWS specifics
- [ADDING_A_SCHEME.md](docs/ADDING_A_SCHEME.md) — fork this for another state
- [VERIFICATION.md](docs/VERIFICATION.md) — what was verified, by whom, and what was not

## Licences

- Code: Apache-2.0, see [LICENSE](LICENSE)
- Scheme corpus in `/schemes/`: CC-BY-4.0, see [schemes/LICENSE](schemes/LICENSE)
