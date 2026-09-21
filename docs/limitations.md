# Limitations

Jev Native MCP deliberately has a narrow contract. The following constraints
are part of the product, not edge cases to route around.

## Hosted inference

- Decision payloads leave the MCP server and are processed by TypeSafe.
- A loopback, LAN, or VPN MCP route protects only the client-to-server hop.
- There is no local model, offline mode, or provider fallback.
- Provider availability, retention, terms, pricing, rate limits, and model
  behavior are external dependencies and may change.
- The server pins `jev-1.13.0`, but the provider still returns the actual model
  ID and may reject or retire a model. Pinning reduces alias drift; it does not
  make answers deterministic.

Only public or synthetic non-sensitive content belongs in the hosted tools.
Private or confidential inputs are out of scope for this release. Supporting
them would require a separately reviewed backend and data-handling contract;
changing the `data_class` string cannot enable that support.

## Local content screening

The local screen matches selected credential patterns. It is not a general
secret scanner, PII detector, confidentiality classifier, or sanitizer.

It can miss encoded, fragmented, unusual, or context-dependent secrets. It can
also reject harmless text that resembles a credential. Callers remain
responsible for a clean input set and the right to send it to the provider.

## Semantic reliability

Strict schemas prevent out-of-contract values; they do not make a decision
correct. Jev output can be wrong, unstable, overconfident, or affected by:

- ambiguous or contradictory criteria;
- irrelevant context and long-list position;
- candidate ordering and batch depth;
- adversarial or authority-claiming candidate text;
- literal readings, indirection, negation, or missing context;
- language and domain shift; and
- model or provider changes.

Confidence is not answerability. A high probability is not evidence. Calls may
vary, so qualify a lane with repeated frozen evaluations.

Do not rely on Jev for arithmetic, counting, date comparison, exact parsing,
hashes, hard policy, authentication, authorization, or irreversible actions.

## Authority boundary

The server returns advice only. It cannot establish:

- permission or scope;
- factual truth or source authenticity;
- safety, cleanliness, or absence of an issue;
- exploitability, impact, severity, or reportability;
- approval to run a tool or perform a browser action; or
- permission to submit, publish, delete, purchase, or change state.

Low-ranked material must remain available. Missing or malformed output is an
error, not a zero score or an empty result.

## Input limits in 0.4.0

The live `jev_health` result is authoritative for the running server. Current
source limits are:

| Limit | Value |
| --- | ---: |
| Serialized state | 50,000 characters |
| Questions in `jev_decide` | 1–60 |
| Ranking or batch candidates | 1–30 |
| Selection options | 2–30, before server-added escape routes |
| Candidate text | 1,600 characters |
| Goal, predicate, or signal instruction | 1,000 characters |
| Claim | 2,000 characters |
| Evidence span | 12,000 characters |
| Stable ID | 80 ASCII letters, digits, dots, underscores, or hyphens |
| Signal-matrix cells | 1–60 |
| MCP request body | 256 KiB |

`Choice` accepts 2–255 declared criteria and `Score` accepts 2–10 levels.
Oversized inputs fail locally. Do not truncate decision-relevant text silently;
split or redesign the workflow and re-evaluate it.

## Ranking and batching

- When `top_k` is omitted, rank and batch tools use `min(10, candidate_count)`;
  an explicit value must remain within the candidate count.
- `top_k` is tie-safe: `effective_top_k` can be larger than requested.
- Scores from separate calls or batches are not guaranteed to share a global
  calibration scale.
- `match_exists` is a probability, not a Boolean coverage result.
- Stable IDs reduce addressing ambiguity but do not prove order invariance.
- Complete ID preservation does not prove the model considered every item
  correctly.

For a queue larger than 30 candidates, use deterministic retrieval or bounded
batches. Any cross-batch merge is advisory and requires its own evaluation.
If a later source-audit batch fails, the CLI returns an incomplete report with
completed receipts and known cost rather than claiming that no call occurred;
the failed batch's provider outcome may remain unknown.

## Transport and access control

- The server has no built-in client authentication.
- The server has no TLS listener.
- Public and wildcard binds are rejected, but a private address alone is not an
  access-control system.
- Hostnames and link-local addresses are rejected even when they resolve or
  route only inside a private network.
- The provider client ignores ambient proxy settings, so proxy-only egress
  environments require an explicit reviewed design change.

Use loopback or a controlled private route and firewall. Do not expose the
included server to the public internet.

## Client approval behavior

Hosted decision tools are intentionally non-read-only and open-world. Some MCP
clients will ask for approval; a deny-all policy may block them. `jev_health`
can still work because it is read-only.

This is expected behavior. Do not bypass it with a direct provider call or a
false read-only annotation.

## Budget accounting

The daily budget is a local estimate, not an invoice or provider-side hard cap.
It uses provider-reported input tokens after valid responses and a conservative
UTF-8 byte estimate before calls and for malformed successes.

The cost rate is fixed in the running source and can drift from current provider
pricing. Verify pricing before relying on the estimate. The budget lock is
process-local; multiple server processes must not share one budget file.

Budget and receipt stores are checked before egress. A disk failure can still
occur after a provider response; the server reports that as local persistence
failure and blocks further paid calls instead of retrying automatically.

## Receipts

Receipts intentionally omit request content. This improves privacy but means a
receipt alone cannot reconstruct or prove what was reviewed. Keep corpus hashes
and evaluation artifacts in an appropriate separate system without secrets.

Within one retained daily file, the HMAC chain detects mutation, reordering,
and deletion of an internal row when a later retained row remains. It does not
detect truncation of a valid tail or deletion of the whole ledger without an
external authenticated record of the expected final HMAC.

The ledger also:

- stores unencrypted operational metadata;
- depends on filesystem permission semantics;
- uses a separate operator-supplied HMAC key;
- cannot validate an existing chain after that key changes; and
- is designed for one writer process per receipt directory.

An outcome record is telemetry supplied after independent review. It does not
prove that the review or model label was correct.

## Release packaging

The packager includes only paths in `release-files.txt`, verifies that inventory
against tracked files when Git metadata is available, refuses symlinks, and
scans included content for selected secret patterns. It cannot prove that every
listed file is safe or public. Review the positive inventory, manifest, and
archive before release.

The archive includes current Codex compatibility and Claude Code manifests.
Codex CLI `0.155.0-alpha.9.2` loaded both skills and discovered the candidate
MCP server from the portable marketplace. Claude manifest validation passed,
but live pickup remains unverified because the available Claude Code `2.0.65`
timed out on its no-plugin control request as well as the plugin attempt.
Packaging conventions can change; validate against the installed client before
distribution.

## Non-affiliation

This repository is an independent integration, not an official TypeSafe,
Codex, or Claude product. It makes no warranty about third-party services or
client behavior.
