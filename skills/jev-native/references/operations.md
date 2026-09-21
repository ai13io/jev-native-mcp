# Jev Native operations

## Deployment modes

The same server runs in either mode:

- local workstation: bind `127.0.0.1:8765` and point the client at loopback;
- remote private server: bind an explicit private VPN/LAN IP and point clients
  at that address.

Wildcard, hostname, and public-IP binds are rejected. Do not expose this MCP
directly to the public internet. A public deployment needs a separately
reviewed HTTPS/authentication boundary that is not included here.

Accepted public/synthetic decision payloads are forwarded to the hosted
TypeSafe API. The server pins `jev-1.13.0` to reduce alias drift, not to make
answers deterministic.

## Runtime state

Configure explicit paths outside the repository:

- budget ledger: `JEV_BUDGET_PATH`;
- authenticated receipt ledger: `JEV_RECEIPT_DIR`;
- TypeSafe key: protected environment or the macOS Keychain launcher;
- receipt HMAC key: `JEV_RECEIPT_HMAC_KEY`, a separate stable secret containing
  at least 32 UTF-8 bytes.

The receipt key must not derive from the provider key. Keep it unchanged across
provider-key rotation; losing it makes existing receipt ledgers unverifiable.
Never store either key in the repository or a release archive.

Receipt events contain a request HMAC and a per-file metadata chain, not
payloads, source text, IDs, paths, prompts, or free-form notes. The chain checks
retained row order and content but cannot detect valid-tail truncation or whole
ledger deletion without an external authenticated head. Outcomes remain
telemetry rather than proof that a label is correct.

## Health contract

Call `jev_health` before paid decisions. Require:

- expected server and contract versions;
- backend class `hosted` and provider `typesafe`;
- `private_data_enabled=false`;
- fallback `disabled`;
- data classes only `public` and `synthetic`;
- live input limits and retry policy.

Use OS-native logs:

- macOS: launchd stdout/stderr files configured in the plist;
- Linux: `journalctl -u jev-native-mcp.service`;
- foreground: the current terminal.

Cross-platform deployment and acceptance instructions live in
`docs/deployment.md` and the linked operating-system guides. Client endpoint
configuration is documented in `docs/client-setup.md`.

## Update procedure

1. Preserve the existing secret store and runtime data directory.
2. Replace the reviewed source tree.
3. Rebuild or reuse its virtual environment only after dependency review.
4. Run `pytest`, plugin/skill validation, and `verify_release.py`.
5. Restart the service and call `jev_health` plus one synthetic fixture.
6. Reinstall the client plugin in a new Codex or Claude session.

Never copy credentials, budget ledgers, receipts, caches, or virtualenvs into a
release archive.

## Failure behavior

- provider unavailable: fail the Jev path and preserve the ordinary workflow;
- budget exhausted: reject paid calls while health remains available;
- malformed HTTP-success: charge one conservative upper bound and record one
  provider-error receipt while storage remains healthy;
- invalid runtime store at startup or preflight: make no provider call, preserve
  the damaged file, repair permissions/content explicitly, and restart;
- persistence failure after a provider response: report known attempts and
  estimated cost, block further paid calls, and never retry automatically;
- unavailable private route: do not add public ingress as a workaround;
- missing/duplicate output: fail loudly, never translate it to zero;
- `429` or `529`: use only the bounded server retry policy;
- exact-response caching remains disabled because it would hide variance and
  preserve stale judgments.
