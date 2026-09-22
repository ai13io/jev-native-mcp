# Deployment

Jev Native MCP runs as a Python 3.10+ Streamable HTTP server. Use loopback when
the MCP client is on the same machine. For a separate server, use one explicit
RFC 1918 or IPv6 ULA address on a controlled VPN or LAN.

The server has no built-in client authentication or TLS listener. Public,
wildcard, hostname, link-local, and unspecified binds are rejected. Do not
expose the included service to the public internet.

## Clean installation

Clone the published repository or extract its source archive, enter the project
root, and create a virtual environment. For the ready-made portable release,
the equivalent plugin root is
`jev-native-portable-0.4.0/plugins/jev-native`; the outer bundle directory is
used only as a Codex marketplace root.

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

Then follow the foreground or service path for the server operating system:

- [macOS foreground and launchd](deployment-macos.md)
- [Linux foreground and systemd template](deployment-linux.md)
- [Windows foreground launcher](deployment-windows.md)

Foreground clean-install and MCP transport smokes passed on macOS/Python 3.12
and Kali Linux/Python 3.14. The Linux run also completed one tiny synthetic
provider decision and receipt check. macOS launchd, Linux systemd, and the
Windows launcher remain documented but not live-verified for this tree. The
checked-in CI matrix is configured for all three operating systems, but those
jobs are not evidence until they run.

## Required configuration

| Variable | Requirement |
| --- | --- |
| `TYPESAFE_API_KEY` | Hosted provider credential; never place it in client or repository files |
| `JEV_RECEIPT_HMAC_KEY` | Independent secret containing at least 32 UTF-8 bytes; keep it stable for the receipt history |
| `JEV_MCP_HOST` | `127.0.0.1`, another loopback address, one RFC 1918 address, or one IPv6 ULA address |
| `JEV_MCP_PORT` | Integer from 1 through 65535; default `8765` |
| `JEV_DAILY_BUDGET_USD` | Optional local input-cost ceiling; default `0.10` |
| `JEV_BUDGET_PATH` | Writable usage-ledger path |
| `JEV_RECEIPT_DIR` | Writable receipt directory used by one server process |

Changing the provider key does not require changing the receipt key. Changing
or losing the receipt key makes existing receipt rows unverifiable.

## Local and private-server profiles

For same-machine use:

```text
JEV_MCP_HOST=127.0.0.1
JEV_MCP_PORT=8765
http://127.0.0.1:8765/mcp
```

For a separate private server, choose one address assigned to that server and
use it consistently in the service environment, firewall policy, and client
URL. Example:

```text
JEV_MCP_HOST=10.42.0.8
JEV_MCP_PORT=8765
http://10.42.0.8:8765/mcp
```

For a plugin artifact, update and validate its `.mcp.json` before packaging:

```bash
python3 tools/configure_profile.py --url "http://10.42.0.8:8765/mcp"
python3 tools/configure_profile.py --check
python3 scripts/verify_release.py
```

The profile tool rejects credentials in URLs, public addresses, wildcard
addresses, hostnames, missing ports, alternate paths, queries, and fragments.

## Client connection

Start the server first, then follow [Client setup](client-setup.md). That guide
separates:

- direct MCP connections, which expose tools only;
- Claude Code's local `--plugin-dir` path; and
- Codex's packaged local-marketplace path.

Restart the client or open a new session after changing the plugin or MCP
configuration. A running pre-install session is not a valid discovery test.

## Acceptance check

A deployment is usable only after a new client session:

1. discovers all eight `jev_*` tools;
2. calls `jev_health` successfully;
3. reports server `0.4.0`, contract `jev-native-0.4`, hosted TypeSafe backend,
   and model `jev-1.13.0`;
4. reports only `public` and `synthetic`, with private data disabled and no
   fallback;
5. reports the expected live limits and retry policy; and
6. keeps decision tools subject to the client's external-action approval.

Use a synthetic fixture for any decision smoke. The release candidate completed
one tiny `jev_rank` call through the universal server on Kali loopback: TypeSafe
returned pinned `jev-1.13.0`, all three candidate IDs were preserved, and one
budget event plus request-body-free receipt were written. This verifies the path,
not semantic ranking quality or another deployment.
