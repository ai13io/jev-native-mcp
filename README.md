# Jev Native MCP

**Turn public code and document collections into traceable review queues for
Codex and Claude Code.**

When an agent has many release notes, source chunks, public issues, or claims to
review against the same semantic question, Jev Native MCP provides a repeatable
first-pass workflow. It prepares bounded batches, applies typed Jev decisions,
keeps stable references to every original item, and helps the agent verify its
conclusions against exact source passages.

Use it when this review repeats often enough to justify a separate hosted
decision step. For a small one-off question, ordinary Codex or Claude reasoning
is usually the better tool.

**Status:** 0.4.0 release candidate. By default, Jev runs alongside the existing
review process and does not change reading order until its results have been
compared with a baseline.

**Requirements:** Python 3.10+, TypeSafe API access, and a compatible MCP
client. Decision inputs go to TypeSafe's hosted API; this release accepts only
non-sensitive public or synthetic material.

## What you can do

- **Build a focused reading queue.** Rank public source or documentation while
  retaining every original item, stable ID, cutoff tie, skipped region, and
  failed batch for follow-up.
- **Apply one question across a collection.** Screen a frozen corpus for a
  behavior, classify public issues, or identify release notes that may require
  application changes.
- **Check conclusions against sources.** Compare an exact claim with an exact
  passage as `supports`, `contradicts`, or `insufficient`, then inspect the
  original yourself.
- **Decide whether Jev deserves a place in the workflow.** Start by observing
  its output without changing the existing process. Let it reorder work only
  after it meets evaluation criteria defined before the trial.

## A review workflow in practice

Suppose you are preparing a migration checklist from public release notes and
upgrade guides. The important changes are described in different language, and
you need to know which documents deserve attention before writing the checklist.

Ask the host agent:

> Review these public release notes for changes that may require application
> updates. Build a first-pass queue, retain the source references, and check
> each proposed checklist claim against its original passage.

The agent gathers the public documents. Jev Native MCP supports the repeated
judgments between collection and final analysis:

```text
public release notes and guides
          ↓
stable source references and bounded batches
          ↓
per-item signals and a first-pass review queue
          ↓
agent reads originals and checks proposed claims
          ↓
migration checklist with sources and unresolved questions
```

The final artifact is still written and verified by the host agent. The package
provides the ranking, batch screening, source addressing, claim checks, and
evaluation record. Unprocessed items, skipped regions, ties, and failed batches
remain visible instead of disappearing from the result.

This is a workflow illustration, not a benchmark or recorded migration result.
Use the bundled evaluation tools to compare it with the existing review process
before allowing Jev rankings to change reading order.

## What is included

| Component | What it adds |
| --- | --- |
| MCP server | Eight bounded tools for health, decisions, ranking, batch predicates, claim review, proposal selection, signal matrices, and local outcome recording |
| `jev-native` skill | General routing rules for repeated public or synthetic decision work |
| `jev-pentest` skill | Security-specific source triage, OSINT reranking, claim/evidence review, and adoption gates without granting Jev testing authority |
| Public-source runner | Deterministic inventory and local screening before exhaustive bounded batches, with truthful partial-failure accounting |
| Evaluation harness | Independent result validation, repeatability metrics, frozen fixtures, and shadow-to-advisory qualification support |
| Runtime controls | Exact model pin, strict response validation, bounded retries, daily budget, persistence preflight, and request-body-free receipts |
| Portable release | Codex marketplace, Claude plugin, macOS/Linux/Windows guides, verified file inventory, manifest, and deterministic ZIP |

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
                         +-- local budget and request-body-free receipt metadata
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

After health succeeds, one tiny synthetic request with stable IDs is an optional
paid end-to-end smoke for the provider, receipt, and result path.

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

## Current verification

The server, installed-package MCP transport, a tiny live TypeSafe decision, and
Codex portable-plugin pickup have been exercised on macOS and Kali Linux.
Windows, persistent service templates, and Claude live pickup remain explicitly
unverified. Versions, results, and boundaries are recorded in
[Verification](docs/verification.md); they are evidence for those configurations,
not a claim that every deployment works.

For concrete workflow placement and boundaries, see [Use cases](docs/use-cases.md)
and [Limitations](docs/limitations.md). Development, full test, and release
commands live in [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation

- [Deployment overview](docs/deployment.md)
- [Client setup](docs/client-setup.md)
- [Architecture](docs/architecture.md)
- [Security model](docs/security-model.md)
- [Use cases](docs/use-cases.md)
- [Limitations](docs/limitations.md)
- [Verification](docs/verification.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## Independence and license

This independent project is not affiliated with, endorsed by, or maintained by
TypeSafe, OpenAI, or Anthropic. Product names may be trademarks of their
respective owners. Hosted use remains subject to the provider's current terms,
policies, availability, and pricing.

Licensed under Apache-2.0. See [LICENSE](LICENSE).
