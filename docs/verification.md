# Verification

This page records what release 0.4.0 has actually exercised. It is evidence for
the named configuration, not a portability or semantic-quality guarantee.

The portable ZIP and SHA-256 checksums are attached to release tag
`v0.4.0-rc4`.

## Verified paths

| Surface | Evidence | Status |
| --- | --- | --- |
| Unit and release contracts | 186 tests and 19 subtests with pytest 9.0.3 on macOS/Python 3.12; the same 186 tests on Kali Linux/Python 3.14 | Verified |
| Installed package | Clean installation outside the source checkout; dependency checks passed | Verified on macOS and Linux |
| MCP transport | Real initialize and list-tools handshake returned all eight tools | Verified on macOS and Linux |
| TypeSafe path | One tiny synthetic `jev_rank` returned pinned `jev-1.13.0`, preserved all three IDs, and wrote one budget event plus one request-body-free receipt | Verified on Kali loopback |
| Codex portable plugin | Codex CLI `0.155.0-alpha.9.2` loaded both bundled skills and discovered/called the candidate `jev_health` tool | Verified on macOS |
| Package reproducibility | Git and extracted-tree builds were byte-identical; positive inventory and manifest hashes matched every source file | Verified |

The live TypeSafe call used synthetic documentation cards. It consumed 484
input tokens in one attempt with an estimated input cost of `$0.000020328`.
That confirms the transport, validation, budget, and receipt path—not ranking
quality.

## Not yet verified

| Surface | Current evidence |
| --- | --- |
| Windows foreground launcher | PowerShell parses and unit tests pass; no hosted Windows run has completed |
| macOS launchd | Template and static checks only |
| Linux systemd | Template and static checks only |
| Claude Code live pickup | Manifest validation passed; available Claude Code `2.0.65` timed out on the same no-plugin control request and plugin attempt |

The checked-in GitHub Actions matrix targets Ubuntu/Python 3.10 and 3.13,
macOS/Python 3.12, and Windows/Python 3.12. A configured job counts only after
the hosted runner executes it successfully.

## Test-suite breakdown

| Suite | Passed |
| --- | ---: |
| Server, receipts, provider contracts, and eval runner | 131 |
| Endpoint profile | 16 |
| Positive-inventory packaging | 13 |
| Public-source audit | 17 |
| Source-audit evaluator | 9 |
| **Total** | **186** |

The macOS pytest 9.0.3 run also reported 19 successful subtests. The canonical
commands are maintained in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Release checks

- source and extracted-archive public-release scans;
- exact positive inventory versus the Git tracked tree;
- archive path, size, and SHA-256 manifest verification;
- duplicate, traversal, symlink, unexpected-file, runtime-state, and selected
  credential-pattern checks;
- byte-identical rebuild from both Git checkout and extracted portable ZIP;
- Codex and Claude manifest validation; and
- independent code, release/security, and editorial review.

Semantic adoption remains lane-specific. Use the frozen evaluation process in
the bundled skills before allowing Jev output to change review order.
