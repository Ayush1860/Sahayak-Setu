# Sahayak Setu

An interview, not a search box. A person describes their work in Hindi. The
app asks two or three short questions, then returns the government schemes
they may be eligible for, each with the criterion they meet, the page of the
source document it came from, and which office to walk into.

**Eligibility is decided by plain Python, never by a model.**

## The problem

Indian government schemes exist for people who do not know they exist. A man
making dona-pattal, leaf plates, at home in a village in Madhya Pradesh is
eligible for subsidised credit, capital subsidy and power-tariff concessions,
and pays full rates because nobody told him.

The source documents are hostile to access. The MP MSME Development Policy
2025 is a 56-page, 59 MB PDF exported from CorelDRAW with zero extractable
text. Every page is an image. Not searchable, not selectable, invisible to a
screen reader. It is in English, for a scheme aimed at rural micro-enterprise.

A search box does not help someone who does not know the name of the thing
they are searching for. So the app asks.

## Three rules the code enforces

**1. Eligibility is decided by code.** [api/matcher.py](api/matcher.py) reads
structured eligibility blocks and returns a verdict. It imports nothing that
can reach a network, and a test asserts that by parsing its own imports. The
model converts language into a profile before it runs, and writes the
explanation after. It never decides who qualifies.

**2. Every answer cites a verified source with a date.**
[api/validator.py](api/validator.py) runs after the model. Every scheme id
must be in the matched set and every URL must be in that scheme's
`source_urls`. Anything else is deleted. Citations are attached from the
corpus, never copied from the model, so a URL physically cannot reach a user
unless a human put it in a scheme file.

**3. Out of scope means refusal.** When nothing survives validation, the
response is a plain statement that we did not find anything, plus the office
to ask at. Never a confident guess.

Three verdicts exist. The strongest is **"likely eligible, confirm at the
office"**. Nothing in this system tells anyone they are entitled to anything,
because only an officer with the documents in hand can say that.

## Architecture

```
  browser (React on Amplify)
        |  POST /ask  { conversation, asked }
        v
  API Gateway  ->  Lambda: api/ask_handler.py
        |
        |  1. extractor.py   language -> profile        [model]
        |  2. interview.py   one next question          [no model]
        |  3. matcher.py     who qualifies for what     [no model]
        |  4. explainer.py   profile -> Hindi cards      [model]
        |  5. validator.py   delete the unsupported     [no model]
        |
        +-- S3          verified scheme corpus, cached in /tmp
        +-- DynamoDB    anonymous counters only
        +-- llm.py      Groq, or Bedrock, chosen by one variable

  offline, from a laptop, never at request time:
    pipeline/  Textract -> draft JSON -> hand verification -> schemes/
```

Two model calls per conversation, both for language only. Everything between
them is deterministic.

Deliberately not used: OpenSearch (overkill and a cost liability for five
documents, where matching is deterministic rather than retrieval), Cognito
(no accounts; asking a villager to sign up defeats the purpose), Step
Functions (two calls need no orchestration).

## Privacy

Caste category, gender and income are collected in-session and never
persisted. The profile exists for the duration of one request.

DynamoDB stores counters only: how many queries, how many matched versus
refused, which schemes fired. No message text, no profiles. A test asserts
that no age, income, caste or gender value can reach DynamoDB, and the
Lambda's IAM policy grants `UpdateItem` and nothing else, so a bug cannot
turn the counter table into a data source.

## Running it

```bash
pip install -r schema/requirements.txt -r api/requirements.txt
python -m pytest -q            # 128 tests, no AWS calls
python schema/validate.py      # validate the scheme corpus
```

Click through the whole flow with no model and no AWS account:

```bash
python scratch/dev_server.py
```

then in another terminal:

```bash
cd web && npm install && npm run dev
```

The harness replaces the model with keyword matching. Matcher, validator and
interview are the real ones.

## Deploying

```bash
sam build && sam deploy --guided
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for what `--guided` asks and
what each parameter does.

## Disclaimer

**This is informational only. It is not legal, financial or official advice.**

Scheme content is transcribed from public government documents by hand and
may be out of date, incomplete or wrong. Rules change without notice. Nothing
here confirms that anyone is eligible for anything. Always confirm at the
office named on the card before acting.

The corpus currently shipped contains one placeholder scheme with fabricated
values, flagged `"PLACEHOLDER": true`, which the matcher withholds from
results by design. See [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Licences

- Code: Apache-2.0, see [LICENSE](LICENSE)
- Scheme corpus in `/schemes/`: CC-BY-4.0, see [schemes/LICENSE](schemes/LICENSE)

Fork it for another state. [docs/ADDING_A_SCHEME.md](docs/ADDING_A_SCHEME.md)
is written for exactly that.
