# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

No changes yet.

## 0.4.0 - 2026-09-22

### Added

- Streamable HTTP MCP server for hosted TypeSafe Jev decisions.
- Eight typed tools: `jev_health`, `jev_decide`, `jev_rank`,
  `jev_batch_check`, `jev_select`, `jev_signal_matrix`, `jev_claim_audit`, and
  `jev_record_outcome`.
- Caller-declared public/synthetic allowlisting, bounded request schemas, local
  sensitive-pattern screening, and validated provider responses.
- Stable candidate addressing, complete-set preservation checks, tie-safe top
  sets, explicit `none` and `needs_review` selection routes, and advisory-only
  result markers.
- Local daily budget enforcement, serialized paid calls, and bounded retries
  for provider overload responses.
- Runtime-store preflight and a paid-call latch after local persistence failure.
- Payload-free, HMAC-chained decision receipts and closed-form outcome records.
- General decision and public-source security workflow skills.
- Synthetic evaluation fixtures with independent, fail-loud result-contract
  checks and partial-batch accounting.
- Dynamic omitted `top_k` handling for queues smaller than ten candidates.
- Portable Codex and Claude Code plugin manifests and deterministic,
  inventory-bounded release packaging with selected credential checks.
- Local and private-server deployment guidance for macOS, Linux, and Windows.
- Separate source/portable-root, Claude scope, and Windows-interpreter setup
  paths.
