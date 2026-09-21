# macOS deployment

The macOS paths are a foreground process and a per-user launchd agent. The
foreground loopback transport has been smoke-tested on macOS with Python 3.12.
The launchd path is documented and statically checked but not yet live-verified
for this public tree.

## Install the server

```bash
cd "<PLUGIN_ROOT>"
python3 -m venv server/.venv
server/.venv/bin/python -m pip install ./server
```

Replace `<PLUGIN_ROOT>` with an absolute path. Keep the server directory in a
stable location before installing launchd.

## Foreground

For a short local run, set both secrets in the current terminal without saving
them to a shell profile, then start the server:

```zsh
cd "<PLUGIN_ROOT>"
read -r -s "TYPESAFE_API_KEY?TypeSafe API key: " && printf '\n'
export TYPESAFE_API_KEY
read -r -s "JEV_RECEIPT_HMAC_KEY?Receipt HMAC key: " && printf '\n'
export JEV_RECEIPT_HMAC_KEY
export JEV_MCP_HOST=127.0.0.1
export JEV_MCP_PORT=8765
server/.venv/bin/python server/server.py
```

The receipt key must contain at least 32 UTF-8 bytes. Stop with `Control-C`,
then run `unset TYPESAFE_API_KEY JEV_RECEIPT_HMAC_KEY`.

## launchd with Keychain

Create two Keychain entries. The `-w` option is deliberately last so the
`security` tool prompts instead of receiving a secret in its argument list:

```bash
/usr/bin/security add-generic-password -a "$USER" -s jev-native-typesafe-api-key -U -w
/usr/bin/security add-generic-password -a "$USER" -s jev-native-receipt-hmac-key -U -w
```

Use a generated value containing at least 32 UTF-8 bytes for the receipt key
and keep that value stable when rotating the provider key.

Create private state and log directories:

```bash
mkdir -p "$HOME/Library/Application Support/JevNative"
mkdir -p "$HOME/Library/Logs/JevNative"
chmod 700 "$HOME/Library/Application Support/JevNative"
```

Copy `server/deploy/io.jev-native.mcp.plist.template` to
`$HOME/Library/LaunchAgents/io.jev-native.mcp.plist` and replace every token:

- `__SERVER_DIR__`: absolute `<PLUGIN_ROOT>/server` path;
- `__PYTHON__`: absolute `<PLUGIN_ROOT>/server/.venv/bin/python` path;
- `__KEYCHAIN_ACCOUNT__`: the output of `id -un`;
- `__STATE_DIR__`: the Application Support directory created above;
- `__LOG_DIR__`: the Logs directory created above.

Do not add either secret to the plist. Validate that no token remains, then
load the agent:

```bash
grep -n '__[A-Z_]*__' "$HOME/Library/LaunchAgents/io.jev-native.mcp.plist"
plutil -lint "$HOME/Library/LaunchAgents/io.jev-native.mcp.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/io.jev-native.mcp.plist"
launchctl kickstart -k "gui/$(id -u)/io.jev-native.mcp"
```

The `grep` command must print nothing. Inspect status and logs with:

```bash
launchctl print "gui/$(id -u)/io.jev-native.mcp"
tail -n 100 "$HOME/Library/Logs/JevNative/jev-native-mcp.err.log"
```

Because launchd execution is not yet live-verified for this public tree, treat
the first successful listener and `jev_health` result as part of deployment,
not as an assumed property of the template.

For a remote private profile, replace `127.0.0.1` in the copied plist with the
server's explicit private VPN/LAN address, then configure the client with the
same address. Never replace it with a wildcard or public address.
