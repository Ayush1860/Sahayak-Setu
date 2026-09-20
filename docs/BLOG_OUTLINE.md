# Build blog: outline

Outline only. The prose is yours.

Working title candidates:

- The 59 MB PDF that nobody can read
- Eligibility is code, not a prompt
- What I learned building on AWS for the first time

---

## 1. The man making leaf plates

- Open with him, not with the tech. A specific person in a village in MP,
  making dona-pattal at home.
- He is eligible for subsidised credit, capital subsidy, power-tariff
  concessions. He pays full rates.
- The gap is not money or eligibility. It is that nobody told him.
- The sentence to land early: a search box does not help someone who does not
  know the name of the thing they are searching for.

## 2. The discovery that set the constraints

- Found the MP MSME Development Policy 2025. 56 pages, 59 MB.
- Zero extractable text. Exported from CorelDRAW. Every page an image.
- What that means concretely: not searchable, not selectable, invisible to a
  screen reader, useless to any tool.
- And it is in English, for a scheme aimed at rural micro-enterprise.
- The point worth making: this is not neglect of the document. It is a
  document produced for a designer's workflow and published as if that were
  the same as publishing information.

## 3. Why the model does not decide eligibility

- The obvious build: put the PDF in a RAG pipeline, let the model answer.
- Why that is wrong here, stated plainly. A model asked "does this person
  qualify?" will always answer. It answers confidently when rules are
  ambiguous, when the profile is half known, and when it has never seen the
  scheme.
- The stakes: a wrong "yes" costs someone a day of wages and a bus fare. A
  wrong "no" costs them the benefit entirely, and they do not come back.
- What was built instead: the model converts language to a structured
  profile, plain Python evaluates criteria, the model writes the explanation.
- The detail that makes it real rather than a claim: `matcher.py` imports
  nothing that can reach a network, and a test parses its own imports to
  prove it.
- Three-valued logic. Why UNKNOWN had to be a first-class outcome rather than
  a default to false: a field nobody has been asked about cannot rule anyone
  out.
- The strongest verdict the system can return is "likely eligible, confirm at
  the office". Explain why refusing to say "eligible" is a feature.

## 4. Making hallucination structurally impossible

- The validator runs after the model, not as review but as deletion.
- Every scheme id must be in the matched set; every URL must be in that
  scheme's source list.
- The move worth explaining: citations shown to the user are read from the
  corpus, never copied from the model output. A URL cannot reach a user
  unless a human put it in a scheme file.
- The test with the deliberately lying fixture: the model invents PMEGP,
  Mudra Loan and two URLs. All four are deleted. Screenshot it.
- Refusal as the fallback when nothing survives.

## 5. What fought back

Keep this section concrete and in order. It is the most useful part for
another first-timer.

- **Bedrock model ids.** Current Claude models cannot be called by their bare
  model id; they need a cross-region inference profile. The error says
  "on-demand throughput isn't supported", which sounds like a quota problem
  and is not. Wrote a discovery script instead of hardcoding an id.
- **The account wall.** `ValidationException: Operation not allowed` on every
  invoke. Chased it through the wrong hypotheses in order: IAM policy, then
  root user, then the Anthropic model agreement.
- **How it was actually diagnosed.** `get-foundation-model-availability`
  returns `entitlementAvailability: AVAILABLE` and `authorizationStatus:
  NOT_AUTHORIZED` separately, which distinguishes "not entitled", "not in
  this region" and "agreement unsigned" — all of which surface as the same
  opaque error at invoke time.
- **The test that settled it.** Tried an OpenAI model, then Amazon's own
  Nova. Identical failure. Not a provider problem, not a model agreement: an
  account-level hold on a new account.
- **The fix that was not a fix.** The use-case form itself returned "your
  account is not authorized, please create a support case".
- **What that forced, and why it was the right architecture anyway.** One
  file, `llm.py`, one function, `complete(system, messages) -> dict`, two
  implementations. The AWS architecture did not change. The swap is one
  environment variable.
- Smaller ones worth a line each: `aws login` credentials need
  `botocore[crt]` before boto3 can read them; the terminal cannot see a newly
  installed CLI because the parent process captured PATH at launch; model
  access is per region.

## 6. What I would tell myself on Thursday

- Discover ids from the account instead of hardcoding them from a blog post.
- When an error message names a category (validation, access denied), check
  whether the service is using that category accurately before believing it.
- Put the provider behind an interface on day one. Not for portability in the
  abstract, but because the thing you cannot control will be the thing that
  breaks.
- Least privilege caught a real mistake: the policy scoped to `anthropic.*`
  is what proved the OpenAI failure was mine and not AWS's.

## 7. What is still not done, honestly

- The corpus is one placeholder scheme. Hand verification is the slow part
  and cannot be automated, which is the actual point.
- Textract pipeline written but the output has not been verified.
- Worth stating plainly rather than implying the project is finished.

## 8. Close

- Return to him. The measure is not the architecture diagram. It is whether
  he walks into the District Industries Centre knowing which scheme to name
  and which papers to carry.
- The one line to end on, if it fits: the hard part was never the model. It
  was deciding what the model was not allowed to do.

---

## Screenshots worth having

- The 59 MB PDF with text selection attempted and nothing selectable
- `test_matcher_imports_nothing_that_can_reach_a_network` passing
- The hallucination fixture test passing
- `get-foundation-model-availability` output showing the two conflicting
  fields
- The three identical `Operation not allowed` failures across three providers
- The app on a phone, in Hindi, showing a card with its source page and
  verification date
- The refusal screen, which is the one most demos would hide
