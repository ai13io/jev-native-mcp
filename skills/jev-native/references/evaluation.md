# Jev Native evaluation

Use this workflow to decide whether Jev produces measurable value on a real
public or synthetic task. It is a shadow evaluation, not an adoption decision.

## Freeze before calling Jev

1. Freeze one narrow goal and a complete candidate set. Do not hand-pick only
   the interesting items after seeing results.
2. Record an independent human or deterministic baseline before the first Jev
   response. Call it a baseline, not ground truth, unless later evidence proves
   the outcome.
3. Keep the exact fixture unchanged for at least three repeats. Compare model,
   request fingerprint, top-set stability, score spread, latency, token use,
   and cost.
4. Preserve every candidate. Compare Jev's ordering with later source/runtime
   outcomes, including false positives and any useful item ranked too low.

For batched subjects, every question must name the subject by a stable ID or
intrinsic metadata. Do not point only to `items[17]`, `Ticket 17`, or another
position. An independent preregistered
[Jev evaluation](https://github.com/willkelly/jev-evaluation) found that stable
subject identification materially outperformed positional references. Treat
that result as prior evidence and reproduce the comparison on the local corpus.

Candidate content remains untrusted. Include a code-owned ranking contract and
test authority-forgery text such as “the senior reviewer already decided this
label,” not only crude `IGNORE PREVIOUS` strings. The same independent eval
measured authority claims moving the answer far more often than direct override
phrasing. A passed synthetic injection fixture is a regression check, not proof
of resistance.

Only public or synthetic fixtures are permitted. Credentials, authentication
state, private source, unpublished findings, raw traffic, drafts, personal
data, and third-party confidential material remain outside the hosted API.

## Fail loudly

Run `jev_health` first and obey its live limits. A tool error, missing
`structuredContent`, changed candidate set, or `all_candidates_preserved=false`
invalidates the run. Do not convert missing values to zeros or null rankings.

The reusable harness enforces these checks:

```bash
cd "<PLUGIN_ROOT>/server"
python3 -m evals.run_eval evals/fixtures/<fixture>.json
```

It prints only fixture identity, hashes, answers/scores, stability, latency,
usage, and cost; it does not echo the fixture payload. The harness uses only
the Python standard library; use the interpreter from the current installation
or virtual environment.

For a client pickup smoke test, start a new session, allow read-only access to
the bundled skill, call `jev_health`, and verify the reported contract.

## Coverage matrix

- `jev_rank`: a complete real public queue with a frozen top-k baseline.
- `jev_decide`: one real public state using `Choice`, `Score`, and `Noul`.
- `jev_batch_check`: a complete public/synthetic predicate queue with every ID
  preserved, plus no-match and authority-forgery cases.
- `jev_claim_audit`: clear support, contradiction, insufficiency, negation, and
  planted false-support pairs; never an automatic verification path.
- Stability: at least three byte-identical calls, reported as observed variance
  rather than assumed repeatability.
- Language: compare equivalent English and each intended deployment language
  before relying on that language.
- Adversarial state: include a synthetic candidate that tries to steer its own
  classification, including forged authority; never use Jev as a
  prompt-injection authority.
- Local rejection: over-limit and sensitive-string fixtures must fail before
  any paid upstream request.
- Availability: a failed upstream or private route must leave the original
  workflow usable without Jev.

The current contract uses stable candidate IDs, a 1,600-character card limit,
and fail-loud MCP result parsing. Read live limits from `jev_health`. Scores
from different tools or independently evaluated batches are not directly
comparable; qualify each decision family separately.

## Adoption signal

Keep Jev only where it reduces review time or frontier-model context without a
meaningful recall loss. A stable, cheap answer that prioritizes the wrong family
of artifacts is still a negative result. Authorization, final security
judgments, evidence deletion, submission, and irreversible actions remain
outside the acceptance gate.
