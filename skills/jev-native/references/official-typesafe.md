# Official TypeSafe reference map

Verified against the official documentation on 2026-09-21. Model aliases,
price, limits, and service behavior are time-sensitive; refresh these pages
before changing the pinned model, thresholds, or production budget.

## API and primitives

- [API reference](https://docs.typesafe.ai/api): `POST /v1/systemone`, request
  and response shapes, errors, and retry guidance.
- [Quick start](https://docs.typesafe.ai/introduction/quickstart): direct HTTP,
  Python/JavaScript SDKs, and the official agent skill.
- [Primitives](https://docs.typesafe.ai/primitives): `Noul`, `Choice`, and
  `Score`. Questions share one state but are evaluated independently.
- [State](https://docs.typesafe.ai/concepts/state): string, object, or array
  input; text only; separate supplied facts from the questions.

The native MCP pins `jev-1.13.0`. It exposes a deliberately smaller contract
than the full SDK: bounded public/synthetic decisions and rankings, with local
screening and a daily budget.

## Current model contract

- [Models](https://docs.typesafe.ai/models): as of the verification date,
  `jev-1.13.0`, `$0.042/M` input tokens, free output, 64k tokens per request,
  and 32k tokens for state plus the longest question. The official page warns
  that rate limits can change without notice.
- `jev-latest` is movable. A version pin reduces alias drift but does not make
  answers deterministic. Log the model returned by every response.
- `GET /v1/models` currently lists aliases. Versioned IDs remain callable even
  when they are absent from that listing, so health accepts a documented Jev
  alias while paid responses must still report the exact pinned model.
- English is the primary training language. Test every intended deployment
  language separately instead of assuming parity.

## Known failure modes

Read [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
before designing a workflow. The vendor documents literal readings, weak
arithmetic/counting/date comparisons, loss from indirection and irrelevant
context, susceptibility to adversarial state, contradictory criteria, lack of
logical invariants between separate questions, and no useful text generation.

Keep deterministic math, dates, counts, policy, authorization, and irreversible
actions in code. Treat type correctness as schema correctness, not semantic
correctness.

## Errors and agent integration

- Official HTTP guidance says `429` and `529` should be retried with bounded
  backoff. The native MCP handles that centrally.
- [Agent skill](https://docs.typesafe.ai/agent-skill) provides API design
  instructions for Claude Code, Codex, and other agents. It does not itself add
  tools, intercept model routing, or turn Jev into a reasoning coprocessor.
- The local `jev-native` skill is intentionally stricter than the official
  generic skill because it preserves this project's hosted-data and decision
  boundary.

For data handling and ZDR availability, follow the official links from the
[Models page](https://docs.typesafe.ai/models) to the current legal documents;
do not infer enterprise ZDR for the standard account.
