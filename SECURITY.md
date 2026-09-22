# Security policy

Jev Native MCP sits between an MCP client and a hosted decision provider. A
security report may affect the local server, its transport boundary, provider
credentials, request validation, release packaging, or receipt integrity.

## Supported versions

Only the current release line receives security fixes.

| Version | Supported |
| --- | --- |
| `0.4.x` | Yes |
| Earlier versions | No |

## Reporting a vulnerability

Report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/ai13io/jev-native-mcp/security/advisories/new).
Do not include vulnerability details, credentials, or private data in public
issues or pull requests.

A useful private report contains:

- the affected version and deployment mode;
- a concise description of the boundary that fails;
- reproducible steps using synthetic data;
- the realistic impact and required attacker position;
- relevant logs with secrets and private content removed; and
- a suggested fix, if known.

No response-time or bounty commitment is implied.

## What belongs here

Report issues in this repository, including:

- public or wildcard network exposure that bypasses the documented bind rules;
- credential disclosure or inclusion in a release archive;
- a hosted decision call that can be made without the expected client-visible
  egress annotation;
- request validation or sensitive-string screening bypasses that materially
  weaken a documented local guard;
- stored payload, source text, identifiers, or free-form notes in the receipt
  ledger;
- receipt-chain integrity failures;
- response-validation failures that turn malformed provider output into a valid
  decision; or
- path, symlink, or packaging behavior that reads or ships files outside the
  intended release.

Security issues in TypeSafe's service, Codex, Claude Code, an operating system,
or another dependency should be reported to that project's owner. This project
does not authorize testing third-party services.

## Operational security

- Never expose the included MCP server directly to the public internet. It has
  no built-in user authentication or TLS termination.
- Run it on loopback or an explicitly private address behind a trusted private
  route. Network location is not a substitute for access control on an
  untrusted LAN.
- Keep `TYPESAFE_API_KEY` out of the repository, client configuration, logs,
  shell history, and release artifacts.
- Generate a separate `JEV_RECEIPT_HMAC_KEY` containing at least 32 UTF-8 bytes,
  protect it as a secret, and keep it stable for the lifetime of its receipt
  history.
- Set absolute runtime paths outside the checkout and restrict access to the
  service account.
- Treat the local sensitive-string screen as a final tripwire, not as a
  sanitizer or data-loss-prevention system.
- Send only public or synthetic non-sensitive content to hosted decision tools.
- Review provider terms and data handling before use.
- Preserve normal client approval for hosted decision tools.

The full boundary is documented in [docs/security-model.md](docs/security-model.md).
