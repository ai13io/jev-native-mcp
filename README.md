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

## Why this project exists

Jev exposes fast typed decisions, but an API primitive alone does not give an
agent an explicit operating contract. A useful integration still has to decide what
may leave the machine, preserve every candidate, reject malformed responses,
control spend, survive partial failures, and show an operator what happened.

Jev Native MCP supplies that missing operational layer:

- **Native agent tools, not prompt snippets.** Codex, Claude Code, and generic
  MCP clients receive real typed tools through Streamable HTTP.
- **Complete-set review.** Rankings retain every stable ID, expand cutoff ties,
  and never turn a low score into permission to discard evidence.
- **Fail-loud contracts.** Missing IDs, impossible probabilities, wrong model
  versions, malformed scores, and incomplete batches remain errors—not empty or
  apparently successful results.
- **Controlled hosted use.** Only caller-declared public or synthetic inputs are
  accepted; local screening is a final tripwire before TypeSafe egress.
- **Operational accountability.** The server enforces a local spend ceiling and
  writes request-body-free, HMAC-linked receipts plus closed outcome telemetry.
- **Portable packaging.** One bundle includes Codex and Claude manifests,
  workstation/private-server guides, deterministic packaging, and a positive
  release inventory. Exercised paths are listed in
  [Verification](docs/verification.md).

The intended workflow is deliberately simple:

```text
deterministic inventory -> reviewed cards -> Jev advisory decision
        -> agent reads original evidence -> independent outcome record
```

Jev reduces the first-pass queue. The reasoning agent still owns source
understanding, verification, and every consequential decision.

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

## How it differs

| Alternative | What remains for the integrator | Jev Native MCP |
| --- | --- | --- |
| Official Jev skill | Teaches API usage but does not create a running MCP service or tools | Ships the server, tool contracts, skills, deployment, and release bundle |
| Direct TypeSafe SDK/API | Application must implement validation, data policy, spend control, receipts, and client wiring | Centralizes those controls behind one MCP contract |
| Browser or action automation | Browser control and action execution are outside this project's scope | No browser driver; selection results never execute actions |
| Compaction or model routing | Context mutation and automatic model routing are outside this project's scope | No context deletion or automatic routing; results remain advisory |
| Local Jev-like models | Keep inference local but use a different model and compatibility surface | Uses hosted TypeSafe Jev and makes that egress explicit |

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
