# Security and pentest placement

Use this reference when deciding whether Jev belongs in a cybersecurity,
pentest, bug-bounty, code-audit, OSINT, or agent-evaluation workflow.

## Immediate hosted uses

Only public or synthetic data:

- rank a complete public attack-surface, method, component, or diff-card queue;
- rerank a public BM25/embedding shortlist for OSINT or source retrieval;
- scan a public repository before running unfamiliar code;
- classify public retrieved passages for relevance, contradiction, usable
  evidence, and suspicious instructions;
- audit atomic public/synthetic claims against exact source spans;
- run regression tests over synthetic agent traces and planted failures.

The output changes review order only. Preserve every original, inspect a random
or bottom-tail sample, and require source/runtime proof for every conclusion.

## Private-data uses are out of scope

Active hypotheses, real findings, private traces, reports, raw traffic, programme
rules, scan output, SOC telemetry, and semantic dedup across undisclosed work
require a separately reviewed backend and data-handling contract. They are not
enabled in this release, and changing `data_class` cannot enable them.

Possible local lanes:

- agent/hypothesis queue scheduling with coverage quotas;
- private claim-to-evidence regression;
- private SOC or scanner triage;
- semantic dedup after hashes and embeddings;
- instruction/rule compliance over private diffs.

## Never an authority

Jev never decides:

- authorization, scope, tool permission, or a live action;
- whether no issue exists, severity, CVSS, reportability, submission, or impact
  proof;
- evidence deletion, compaction, or source-of-truth rewriting;
- attack-chain synthesis or final adversarial review;
- dates, counts, hashes, exact limits, arithmetic, or policy allowlists.

Prompt-injection probability is an advisory signal only. Candidate text is
adversarial state. An independent preregistered evaluation found forged
authority and document structure substantially more effective than crude
`IGNORE PREVIOUS` phrasing.

## Question and state design

- Compute formal constraints in code first.
- Name every batched subject by stable ID or intrinsic metadata, never only by
  numeric position.
- Keep source text rather than replacing it with a derived graph or summary when
  the semantic question depends on the source.
- Put labeled examples in state, not inside the instruction text.
- Ask several narrow security signals instead of one final verdict; compose them
  in reviewed code.
- Use one joint Choice where outcomes are mutually exclusive.
- Do not infer that the state was answerable from confidence alone.
- Fit thresholds on frozen labeled development data, then evaluate a heldout.
- Pin the model and log raw probabilities, usage, latency, fingerprint, and
  source hashes.

Primary research anchors:

- [jev-sec-bench](https://github.com/Gaurav-Gosain/jev-sec-bench)
- [jev phishing benchmark](https://github.com/anisselbd/jev-phishing-bench)
- [willkelly/jev-evaluation](https://github.com/willkelly/jev-evaluation)
- [BorisLeMeec/jev](https://github.com/BorisLeMeec/jev)
- [Hunch research](https://github.com/Kelbie/hunch/blob/main/docs/semantic-search-research.md)
- [TypeSafe reranking cookbook](https://docs.typesafe.ai/cookbooks/rerank_typesafe)

## Acceptance gate

Before adoption:

The numerical thresholds below are conservative starter policy. A deployment
may preregister different or stricter gates for its own miss cost before the
first result is observed; they are not vendor performance guarantees.

1. Freeze the complete corpus and human/deterministic baseline before inference.
2. Run at least three identical repeats and an order/addressing regression.
3. Preserve all IDs and audit low-ranked items.
4. Compare with code, `rg`, BM25/embeddings, and a frontier model.
5. Use a separate heldout with real outcomes.
6. Require at least 30% time/context/cost improvement without a meaningful
   recall loss; for source ranking target useful-item recall of at least 95% at
   the declared reading budget.
7. Safety-critical use remains advisory even after a good benchmark.
