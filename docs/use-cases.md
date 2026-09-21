# Use cases

Jev Native MCP is useful when a workflow has a complete bounded set, a narrow
semantic question, and a reason to repeat that judgment. It is most effective
as a typed prefilter before independent review.

It is not a replacement for deterministic parsing, search, static analysis, or
a general reasoning model. If code can answer the question reliably, use code.

## Choose the narrowest tool

| Need | Tool | Result |
| --- | --- | --- |
| Several typed questions over one shared state | `jev_decide` | `Noul`, `Choice`, or `Score` answers |
| Reorder a complete candidate set by one goal | `jev_rank` | Full ranking and tie-safe top set |
| Apply one predicate to every item | `jev_batch_check` | Per-item probabilities and aggregate `match_exists` probability |
| Propose one host-defined route | `jev_select` | One option, `none`, or `needs_review`; never execution |
| Extract several independent features per item | `jev_signal_matrix` | Complete candidate-by-signal probability matrix |
| Compare one claim with one exact span | `jev_claim_audit` | `supports`, `contradicts`, or `insufficient` |
| Record an independently reviewed result | `jev_record_outcome` | Local structured telemetry linked to a receipt |

## General workflows

### Public retrieval reranking

Use deterministic search to produce a bounded public shortlist, then use
`jev_rank` to prioritize what a reviewer reads first.

Good candidate cards contain a stable ID and only relevant public metadata: a
title, source, date already parsed by code, and a faithful excerpt. Keep the
original search order, read primary sources, and sample the low-ranked tail.

Do not treat relevance as truth or compare scores from unrelated calls as one
global scale.

### Repeated semantic screening

Use `jev_batch_check` when one predicate must be applied to every record and the
behavior cannot be expressed reliably with exact parsing.

Examples include:

- whether a public issue description reports a reproducible failure;
- whether a public changelog entry describes a breaking behavior; or
- whether a synthetic support case requires manual policy review.

Freeze the predicate and complete set before the call. `match_exists` is a
probability, not a Boolean. Never discard a low-probability record.

### Bounded proposal routing

Use `jev_select` only after the host has defined every allowed option and
applied hard policy rules. Suitable proposals are non-executing choices such as
which public document to read next or which specialist review queue should see
a synthetic case.

The server always adds `none` and `needs_review`. The host must still verify
current state, permissions, and preconditions before doing anything with the
proposal.

### Atomic claim review

Use `jev_claim_audit` to challenge whether one exact public or synthetic span
supports one atomic claim. Verify the span exists in the frozen source before
the call and read its surrounding context afterward.

`supports` means the model found a supporting relation in the supplied text. It
does not mean the source is authentic, current, complete, or proven.

### Synthetic regression analysis

Use `jev_signal_matrix` to measure independent semantic signals across a
synthetic trace set, such as:

- unsupported completion;
- missing verification;
- repeated loops; or
- drift from a declared policy.

Combine signals only in separately reviewed deterministic code. Evaluate each
signal against held-out labels before operational use.

## Security, pentest, and public-source audit

Security work is a major use case, but the hosted-data and authority boundaries
are strict. Jev can help prioritize **public or synthetic** material before a
security researcher or reasoning agent performs the actual analysis.

Appropriate uses include:

- ranking public source-code cards for manual audit;
- checking one bounded behavior across a clean public repository export;
- reranking public OSINT results or documentation passages;
- comparing an atomic public claim with an exact public source span;
- analyzing synthetic agent traces and planted security failures; and
- extracting independent semantic signals from public or synthetic cards.

A safe public-source audit looks like this:

1. Work from a clean, frozen public export, not an active checkout that may
   contain local secrets or private patches.
2. Inventory and hash the full corpus.
3. Use `rg`, structural queries, and static analysis first.
4. Freeze one behavioral predicate and stable chunk IDs.
5. Inspect the dry-run plan from the bundled public-source audit helper.
6. Send only reviewed public chunks through `jev_batch_check`.
7. Read the selected originals, their callers and callees, and a reproducible
   tail sample.
8. Establish reachability, attacker control, authorization, and impact through
   independent code and permitted runtime evidence.

Useful bounded predicates describe observable behavior, for example whether a
handler binds a requested object to the authenticated tenant before use. Avoid
final-verdict questions such as “Is this vulnerable?” or “Should this be
reported?”

Jev must not decide:

- testing authorization or program scope;
- whether a vulnerability exists;
- exploitability, impact, severity, or CVSS;
- reportability or submission;
- whether evidence can be deleted; or
- any live request, command, browser action, or account operation.

Do not send private program rules, unpublished hypotheses, active findings,
raw HTTP, authenticated dashboards, device data, report drafts, or evidence to
the hosted provider.

The specialized `jev-pentest` skill contains stricter activation gates and
public-source workflow references. Its name reflects the use case, not a grant
of authority.

## Shadow-first adoption

Every new decision family and corpus starts in **shadow**:

1. Freeze the corpus, IDs, baseline, reading budget, metrics, and acceptance
   thresholds before inference.
2. Run the same request at least three times and test candidate ordering and
   list depth.
3. Compare against deterministic methods and the existing no-Jev workflow.
4. Review false negatives and the low-ranked tail.
5. Measure end-to-end time, context use, cost, and useful items recovered.
6. Move only the evaluated lane to advisory ordering when it meets its frozen
   gate.

Shadow output does not change the normal queue or decision. A model, contract,
language, corpus, chunker, or provider-policy change returns the lane to shadow.
There is no automatic-authority state.

## Poor fits

Do not use Jev Native MCP for:

- open-ended research, synthesis, or writing;
- tiny one-off choices that ordinary reasoning handles directly;
- exact strings, dates, counts, arithmetic, hashes, or allowlists;
- private or regulated content under the standard hosted boundary;
- semantic compaction or evidence deletion;
- authentication, authorization, or approval decisions;
- irreversible actions; or
- a final security, legal, medical, financial, or policy judgment.

See [Limitations](limitations.md) before designing a new lane.
