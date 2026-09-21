# Security model

This document describes the security properties of the repository as
implemented in version 0.4.0. It is not a security claim about TypeSafe's hosted
service or any MCP client.

## Security objectives

Jev Native MCP aims to:

- keep the TypeSafe credential on the server;
- reject public, wildcard, and ambiguous listener addresses;
- make hosted egress visible to MCP clients;
- accept only explicitly classified public or synthetic decision material;
- reject common secret patterns before a paid call;
- bound all decision inputs and validate all provider outputs;
- prevent decision results from carrying action authority;
- limit accidental spend and retry storms;
- retain operational receipts without retaining request content; and
- keep credentials and runtime state out of portable release archives.

## Trust boundaries

| Boundary | What is trusted | What is not assumed |
| --- | --- | --- |
| MCP client to server | The configured client and private route | That every client user is authorized, or that a private LAN is safe |
| Server process | Local validation code and protected runtime account | That arbitrary input can be classified correctly by regex |
| Server to TypeSafe | HTTPS transport and the provider response contract | That decision payloads stay on the MCP host, zero retention, semantic correctness, or availability |
| Jev output to workflow | Schema-valid advisory probabilities and labels | Truth, authorization, safety, completeness, or permission to act |
| Local receipt storage | Restricted filesystem permissions and secret HMAC key | Encryption at rest or protection after service-account compromise |

## Hosted-data boundary

Every decision tool requires `data_class="public"` or
`data_class="synthetic"`. The server rejects other values. This is a declaration
by the caller, not automatic classification.

Allowed material is limited to non-sensitive content that may be sent to the
hosted provider, such as:

- public documentation or public source excerpts;
- public, sanitized retrieval cards; and
- intentionally synthetic fixtures.

Do not send:

- credentials, session data, cookies, tokens, OTPs, or private keys;
- personal data or third-party confidential material;
- authenticated pages, account state, mail, private logs, or raw traffic;
- private source code or local uncommitted changes;
- unpublished security hypotheses, active findings, reports, or evidence; or
- any material whose provider processing rights are uncertain.

The regex screen recognizes several common secret forms. It can miss unusual,
encoded, fragmented, or context-dependent secrets. It also cannot identify
ordinary confidential prose. Sanitize and classify before the call; do not use
the screen as a DLP product.

## Network boundary

The server accepts only a numeric loopback, RFC 1918, or IPv6 ULA bind address.
It refuses wildcard, public, hostname, and link-local binds and enables the MCP
SDK's DNS-rebinding protection.

The included service has no client authentication and no TLS listener. Safe
deployment therefore means one of:

- loopback access by a trusted local user; or
- an explicitly private server address reachable only through a reviewed VPN
  or similarly controlled network, with host firewall restrictions.

Do not port-forward the service, publish it through a tunnel, or expose it on a
shared untrusted LAN. If public service is required, add and review an external
authenticated HTTPS gateway; that architecture is outside this repository's
provided security boundary.

The server's outbound provider client ignores ambient proxy environment
variables. This reduces accidental proxy routing but can conflict with networks
that require an approved egress proxy.

## Client approvals and authority

`jev_health` is annotated read-only. Hosted decision tools are deliberately
annotated as non-read-only, non-idempotent, open-world calls because they send
supplied content outside the local MCP boundary. A compatible client can
therefore request approval.

Do not relabel hosted tools read-only to suppress approval. A client configured
to deny all approvals may allow health but block decisions; the safe fallback
is the ordinary non-Jev workflow.

`jev_record_outcome` is a local non-destructive write. It has no open-world
effect.

No Jev result authorizes a command, network request, browser action, submission,
publication, deletion, or other side effect. `jev_select` makes this explicit
with `authorized: false` and `executed: false`. Other tools return probabilities
or labels only. The calling workflow retains its normal permission checks.

## Input and output controls

Inputs are bounded by type, serialized size, collection size, identifier
syntax, and tool-specific constraints. Specialized tools build server-owned
instructions that treat candidate content as untrusted evidence.

Provider output is accepted only when it exactly matches the requested question
IDs and answer types. Probabilities must be finite and within `[0, 1]`;
distributions must contain exactly the declared options and sum to one within a
small tolerance. After JSON decoding, unknown, missing, duplicated answer IDs,
and malformed fields fail the tool path rather than becoming zero scores or
empty results. The standard JSON decoder does not preserve duplicate raw object
member names; the response contract does not claim to detect those before
decoding.

These checks protect structural integrity. They cannot prove that a
schema-valid decision is correct or resistant to adversarial content.

## Spend and availability controls

Paid calls are serialized inside one server process. Before egress, the server
validates the budget and receipt stores and compares a conservative request
estimate with the local daily budget. It records provider-reported input tokens
after a valid success and a conservative charge plus failure receipt for a
malformed HTTP-success while storage remains healthy.

HTTP `429` and `529` responses receive bounded retries. Other failures stop the
call. There is no fallback model or automatic public endpoint. If the provider,
private route, budget, or response contract fails, preserve the original queue
and continue without Jev.

The budget is a local best-effort guardrail. Provider-side limits and billing
remain authoritative.

No preflight can guarantee that a disk write will still succeed after the
provider responds. Such a failure is reported separately from provider failure
with known attempts and estimated cost, and paid calls are latched off to avoid
automatic repeat spend. Operators must preserve and repair the store, then
restart the process; the server never deletes damaged state.

## Receipt privacy and integrity

Decision receipts contain no request body. They store a request HMAC and a
closed metadata schema. Outcome events contain only closed labels, verification
source, item counts, and time estimates. Raw prompts, candidate IDs, source
text, paths, and notes are not accepted.

Daily ledger files are:

- stored under a directory forced to mode `0700` where supported;
- opened without following symlinks where the platform supports it;
- forced to mode `0600`;
- appended and synchronized to disk; and
- chained with an HMAC over every event and the preceding event HMAC.

The HMAC key is an independent `JEV_RECEIPT_HMAC_KEY` secret containing at least
32 UTF-8 bytes. Keep it stable across provider-key rotation. Changing it makes
existing ledger chains unverifiable, so plan receipt-key rotation as a separate
archive boundary.

Within a retained daily file, the chain detects mutation, reordering, and
deletion of an internal row when a later retained row still refers to it. It
cannot detect truncation of a valid tail or deletion of the whole ledger
without an external authenticated record of the expected final HMAC. A process
with the key and write access can also create a new valid chain. Metadata is not
encrypted.

Run one server process per budget path and receipt directory. The in-process
locks do not coordinate independent processes sharing the same files.

## Secret handling

Provide `TYPESAFE_API_KEY` and `JEV_RECEIPT_HMAC_KEY` through the platform's
protected service environment or secret store described in the deployment
guides. Do not place either one in:

- `.mcp.json` or another client manifest;
- committed environment files;
- command examples, test fixtures, or screenshots;
- receipt or budget paths;
- logs; or
- portable bundles.

The release packager admits only the checked-in positive inventory, refuses
symlinks, scans included content for selected secret patterns, and records a
SHA-256 manifest. This is defense in depth, not a replacement for reviewing the
archive before publication.

## Dependency and provider boundary

Runtime dependencies are pinned in `server/pyproject.toml`. Review dependency
changes and regenerate the environment rather than copying an existing virtual
environment into a release.

TypeSafe policies, pricing, data handling, model behavior, and availability can
change independently of this repository. Recheck the provider's current terms
before deployment or a data-class expansion. This project is independent and
does not authorize security testing of the hosted service.

## Safe failure state

The intended failure state is simple: no Jev decision, no changed queue, and no
new authority. A caller should keep its original material and use deterministic
or ordinary review when validation, approval, routing, budget, provider, or
receipt checks fail.
