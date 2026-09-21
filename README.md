# Jev Native MCP

Typed ranking, classification, and claim review with TypeSafe Jev for Codex,
Claude Code, and other Streamable HTTP MCP clients.

Run the MCP server on a workstation or controlled private network. It forwards
reviewed public or synthetic inputs to TypeSafe's hosted API, validates the
responses, and records local usage and receipt metadata. The package contains
eight tools and two optional workflow skills. It is not a general reasoning
engine, local inference server, or authority for consequential actions.

**Status:** 0.4.0 release candidate, shadow-first. Compare Jev output with an
independently reviewed baseline before it changes review order. The pinned
`jev-1.13.0` model reduces alias drift; it does not make responses deterministic
or repeatable.

> Decision inputs are sent to TypeSafe. Use non-sensitive public or synthetic
> data. Results are advisory and must be evaluated against your own baseline.

## Example: prioritize a documentation queue

This synthetic example shows the `jev_rank` contract. It is an optional paid
smoke test, not evidence of ranking quality or a reason to add a model call to a
trivial task.

```json
{
  "data_class": "synthetic",
  "goal": "Find documentation that helps diagnose HTTP request timeouts.",
  "candidates": [
    {
      "id": "timeouts",
      "text": "A guide to connect timeouts, read timeouts, and retry deadlines."
    },
    {
      "id": "formatting",
      "text": "A guide to headings, lists, and formatting in Markdown."
    },
    {
      "id": "storage",
      "text": "A guide to database backups and storage capacity planning."
    }
  ],
  "top_k": 1
}
```

Illustrative excerpt—the probabilities below explain the shape and are not
measured output:

```json
{
  "ranked": [
    {"id": "timeouts", "relevance": 0.94},
    {"id": "storage", "relevance": 0.10},
    {"id": "formatting", "relevance": 0.03}
  ],
  "all_ids": ["timeouts", "storage", "formatting"],
  "top_ids": ["timeouts"],
  "requested_top_k": 1,
  "effective_top_k": 1,
  "all_candidates_preserved": true,
  "candidate_count": 3
}
```

The full response also contains model, usage, timing, receipt, and cutoff
metadata. Every candidate remains available, and a tie at the cutoff may expand
`top_ids` beyond the requested size.

## Tools

| Tool | Purpose | Network behavior |
| --- | --- | --- |
| `jev_health` | Report the server contract, limits, budget policy, receipt summary, and upstream model availability | Calls TypeSafe's model endpoint without a decision payload |
| `jev_decide` | Ask bounded `Noul`, `Choice`, or `Score` questions over one state | Sends the state and questions to TypeSafe |
| `jev_rank` | Rank a complete candidate set by one goal | Sends the goal and candidate cards to TypeSafe |
| `jev_batch_check` | Apply one predicate to every candidate | Sends the predicate and complete candidate set to TypeSafe |
| `jev_select` | Propose one route from host-defined options, `none`, or `needs_review` | Sends the goal and option cards to TypeSafe |
| `jev_signal_matrix` | Score every candidate-by-signal pair | Sends candidate cards and signal definitions to TypeSafe |
| `jev_claim_audit` | Relate one claim to one exact evidence span | Sends the claim and span to TypeSafe |
| `jev_record_outcome` | Attach a closed-form review outcome to a successful receipt | Local write only |

Decision tools are advisory. They preserve the declared option or candidate
set and return probabilities, not permission to discard, submit, execute, or
approve anything.

## Data flow

```text
MCP client -> loopback/private-network server -> hosted TypeSafe Jev API
                         |                 |
                         |                 +-- validated typed result
                         +-- local budget and content-free receipt metadata
```

The client-to-server route may be private, but accepted decision payloads leave
the server for hosted inference. Only non-sensitive `public` or `synthetic`
content is in scope. See [Security model](docs/security-model.md).

## Install

Prerequisites:

- Python 3.10 or newer;
- TypeSafe API access and an API key; start with the
  [official quickstart](https://docs.typesafe.ai/introduction/quickstart);
- a separate receipt HMAC secret containing at least 32 UTF-8 bytes; and
- Codex, Claude Code, or another Streamable HTTP MCP client.

Generate the receipt secret with a password manager or operating-system secret
generator, store it once, and keep it independent from the provider key. Do not
regenerate it on service restart.

### Choose the correct root

For a Git clone or GitHub-generated source ZIP, the repository root is
`PLUGIN_ROOT`:

```bash
git clone https://github.com/ai13io/jev-native-mcp.git
cd jev-native-mcp
```

For the ready-made portable release ZIP, extract it first:

```text
jev-native-portable-0.4.0/       BUNDLE_ROOT: Codex marketplace root
├── .agents/plugins/marketplace.json
└── plugins/
    └── jev-native/              PLUGIN_ROOT: server and Claude plugin root
```

Enter `jev-native-portable-0.4.0/plugins/jev-native` before installing or
starting the server. Use the outer `BUNDLE_ROOT` only for the Codex marketplace
command. Do not rebuild the portable ZIP merely to install it.

### Create the server environment

macOS or Linux:

```bash
python3 -m venv server/.venv
server/.venv/bin/python -m pip install ./server
```

Windows PowerShell:

```powershell
py -3 -m venv server\.venv
& ".\server\.venv\Scripts\python.exe" -m pip install ".\server"
```

### Load secrets and start the server

Use the foreground instructions for
[macOS](docs/deployment-macos.md#foreground),
[Linux](docs/deployment-linux.md#foreground), or
[Windows](docs/deployment-windows.md#start-in-the-foreground). Those commands
prompt for secrets instead of putting them in repository files.

The default endpoint is:

```text
http://127.0.0.1:8765/mcp
```

Keep the server terminal open for the first check.

### Connect a client

For Claude Code tools in every project used by the current account:

```bash
claude mcp add --scope user --transport http jev-native http://127.0.0.1:8765/mcp
claude mcp get jev-native
claude
```

For one project only, run the same command from that project with
`--scope local`. Direct MCP setup exposes tools but does not install the bundled
skills. Inside Claude Code, use `/mcp` to inspect the connection.

For Codex, open **Settings → MCP Servers**, add a Streamable HTTP server named
`jev-native` with the loopback URL, save, and restart the client. In the Codex
TUI, use `/mcp` to inspect the connection.

The plugin paths that also load the bundled skills are documented in
[Client setup](docs/client-setup.md). They include Claude's official
`--plugin-dir` development route and Codex's packaged local-marketplace route.

### Verify in a new session

Ask the client:

```text
Call jev_health and show the structured result. Do not make a decision call.
```

Require:

- `ok: true`;
- server version `0.4.0` and contract `jev-native-0.4`;
- backend class `hosted`, provider `typesafe`, and model `jev-1.13.0`;
- `private_data_enabled: false` and fallback `disabled`;
- data classes `public` and `synthetic`; and
- the expected live limits and retry policy.

`jev_health` confirms provider catalogue access. TypeSafe currently lists model
aliases, so health does not prove that the exact pinned model can complete a
paid decision or that a decision will be correct. If health or discovery fails,
stop the Jev path and fix the installation; do not open a public listener or
call the provider directly from the client.

For a complete-plugin installation, also confirm that both workflow skills are
visible. In Claude Code they are namespaced as `/jev-native:jev-native` and
`/jev-native:jev-pentest`. The direct tools-only path does not provide them.

After health succeeds, the synthetic ranking example above is an optional paid
end-to-end smoke for the provider, receipt, and result path.

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `TYPESAFE_API_KEY` | Yes | none | Server-side TypeSafe credential |
| `JEV_RECEIPT_HMAC_KEY` | Yes | none | Independent receipt-chain secret; at least 32 UTF-8 bytes |
| `JEV_MCP_HOST` | No | `127.0.0.1` | Loopback, RFC 1918, or IPv6 ULA address |
| `JEV_MCP_PORT` | No | `8765` | Streamable HTTP port |
| `JEV_DAILY_BUDGET_USD` | No | `0.10` | Local daily input-cost ceiling |
| `JEV_BUDGET_PATH` | Recommended | `runtime/usage.json` | Usage ledger; services should use an absolute path outside the checkout |
| `JEV_RECEIPT_DIR` | Recommended | `runtime/receipts-v2` | Receipt directory; services should use an absolute path outside the checkout |

## Compatibility evidence for 0.4.0

| Surface | Evidence in this release | Status |
| --- | --- | --- |
| Python server, tools, skills, packaging, and release checks | 186 tests and release validators passed on macOS/Python 3.12 and Kali Linux/Python 3.14 | Verified |
| Installed-package MCP transport | Clean install outside checkout; real MCP initialize/list-tools returned all eight tools on macOS and Linux | Verified |
| Live TypeSafe decision | Tiny synthetic `jev_rank` through the universal server returned pinned `jev-1.13.0`, preserved all IDs, and wrote budget plus receipt metadata | Verified on Kali loopback |
| macOS launchd service | Template and static checks only | Not live-verified |
| Codex local marketplace/plugin pickup | Codex CLI `0.155.0-alpha.9.2` loaded both skills and discovered/called `jev_health` from an isolated portable marketplace | Verified on macOS |
| Claude Code `--plugin-dir` | Manifest validation passed, but Claude Code `2.0.65` timed out even on a no-plugin control `-p` request | Client baseline blocked live pickup |
| Linux foreground server | Clean install, full suite, MCP handshake, health, paid synthetic decision, and receipt checks | Verified on Kali Linux |
| Linux systemd service | Unit template and static checks only; the installed personal service was not changed | Not live-verified for this tree |
| Windows foreground launcher | Launcher and CI job are present; neither CI nor a live launcher run has completed for this public tree | Not verified |

The checked-in CI matrix targets Ubuntu with Python 3.10 and 3.13, macOS with
Python 3.12, and Windows with Python 3.12. A configured job is not evidence that
the job has run.

## Suitable workloads

- Ranking a bounded public documentation or retrieval queue.
- Applying one semantic predicate to a complete set of public records.
- Comparing an atomic public claim with an exact public evidence span.
- Routing among host-defined, non-executing proposals.
- Building a feature matrix over synthetic regression cases.
- Prioritizing public-source code audit, pentest preparation, and security OSINT
  before independent analysis.

Use deterministic parsing, search, static analysis, or ordinary reasoning when
they already express the task. Jev does not decide testing authorization,
scope, exploitability, severity, reportability, or live actions. See
[Use cases](docs/use-cases.md) and [Limitations](docs/limitations.md).

## Development and release checks

Install the development extra, then run:

```bash
server/.venv/bin/python -m pip install -e "./server[dev]"
server/.venv/bin/python -m pytest server/tests
server/.venv/bin/python -m pytest tools/test_configure_profile.py
server/.venv/bin/python -m pytest scripts/test_package_portable.py
server/.venv/bin/python -m pytest skills/jev-pentest/scripts/test_public_source_audit.py
server/.venv/bin/python -m pytest skills/jev-pentest/scripts/test_evaluate_source_audit.py
server/.venv/bin/python scripts/verify_release.py
```

Build the deterministic portable archive with:

```bash
server/.venv/bin/python scripts/package_portable.py --output ../dist/jev-native-0.4.0.zip
```

The output must be outside the source root. The packager includes only the
checked-in release inventory, excludes runtime state and build output, and scans
included files for selected credential patterns. That scan is a tripwire, not a
proof that arbitrary content is public or secret-free. Review the manifest and
checksum before distribution.

## Repository map

```text
server/       MCP server, receipt ledger, tests, and evaluation runner
skills/       General and public-source security workflow skills
tools/        Endpoint-profile helper
scripts/      Release verification and deterministic packaging
docs/         Deployment, architecture, security, use cases, and limits
```

## Documentation

- [Deployment overview](docs/deployment.md)
- [Client setup](docs/client-setup.md)
- [Architecture](docs/architecture.md)
- [Security model](docs/security-model.md)
- [Use cases](docs/use-cases.md)
- [Limitations](docs/limitations.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## Independence and license

This independent project is not affiliated with, endorsed by, or maintained by
TypeSafe, OpenAI, or Anthropic. Product names may be trademarks of their
respective owners. Hosted use remains subject to the provider's current terms,
policies, availability, and pricing.

Licensed under Apache-2.0. See [LICENSE](LICENSE).
