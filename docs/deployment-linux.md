# Linux deployment

Linux has a foreground path and a systemd service template. Neither has been
live-verified for this public tree. The Linux CI jobs are configured but have
not yet run. The default profile is loopback-only.

## Foreground

```bash
cd "<PLUGIN_ROOT>"
python3 -m venv server/.venv
server/.venv/bin/python -m pip install ./server
read -r -s -p "TypeSafe API key: " TYPESAFE_API_KEY && printf '\n'
export TYPESAFE_API_KEY
read -r -s -p "Receipt HMAC key: " JEV_RECEIPT_HMAC_KEY && printf '\n'
export JEV_RECEIPT_HMAC_KEY
export JEV_MCP_HOST=127.0.0.1
export JEV_MCP_PORT=8765
server/.venv/bin/python server/server.py
```

The receipt key must contain at least 32 UTF-8 bytes and remain stable across
provider-key rotation. Stop with `Control-C`, then run
`unset TYPESAFE_API_KEY JEV_RECEIPT_HMAC_KEY`.

## systemd

Install the repository in a stable location readable by a dedicated
unprivileged service account, and create a private state directory. A typical
layout is:

```text
/opt/jev-native-mcp/       application files
/var/lib/jev-native-mcp/   budget and receipt state
/etc/jev-native-mcp.env    root-owned environment file
```

Create the state directory for the dedicated service account before starting
the hardened unit:

```bash
sudo install -d -o <service-user> -g <service-group> -m 0700 /var/lib/jev-native-mcp
```

Create the virtual environment from the server directory and install the
project:

```bash
cd /opt/jev-native-mcp/server
python3 -m venv .venv
.venv/bin/python -m pip install .
```

Copy `server/deploy/jev-native-mcp.env.example` to
`/etc/jev-native-mcp.env`, set mode `0600`, and edit it with a privileged
editor. Fill both secrets; do not pass them to systemd on a command line.

Copy `server/deploy/jev-native-mcp.service.template` to
`/etc/systemd/system/jev-native-mcp.service` and replace every token:

| Token | Example |
| --- | --- |
| `__SERVICE_USER__` | dedicated service account |
| `__SERVICE_GROUP__` | dedicated service group |
| `__SERVER_DIR__` | `/opt/jev-native-mcp/server` |
| `__ENV_FILE__` | `/etc/jev-native-mcp.env` |
| `__PYTHON__` | `/opt/jev-native-mcp/server/.venv/bin/python` |
| `__MCP_HOST__` | `127.0.0.1` |
| `__MCP_PORT__` | `8765` |
| `__STATE_DIR__` | `/var/lib/jev-native-mcp` |

The host and port tokens must match the environment file. Verify the finished
unit before enabling it:

```bash
grep -n '__[A-Z_]*__' /etc/systemd/system/jev-native-mcp.service
sudo systemd-analyze verify /etc/systemd/system/jev-native-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable --now jev-native-mcp.service
sudo systemctl status jev-native-mcp.service
sudo journalctl -u jev-native-mcp.service -n 100 --no-pager
```

The `grep` command must print nothing. For a remote private profile, bind the
unit and environment file to one explicit private VPN/LAN address and restrict
the host firewall to the intended private source range. Do not use a wildcard,
public IP, or public port-forward.

The unit passing `systemd-analyze verify` is a static check. Do not mark the
service operational until it starts on the target host and a new client session
completes `jev_health`.
