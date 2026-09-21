# Client setup

Start the server before configuring a client. The default Streamable HTTP
endpoint is:

```text
http://127.0.0.1:8765/mcp
```

Choose either a complete plugin path, which includes the bundled skills, or a
direct MCP path, which exposes tools only. Do not configure both under the same
server name in one client.

## Codex and the ChatGPT desktop app

### Codex direct MCP connection

In the desktop app:

1. Open **Settings → MCP Servers**.
2. Select **Add server**.
3. Enter `jev-native`, choose **Streamable HTTP**, and enter the endpoint.
4. Save and select **Restart**.
5. In a new session, use `/mcp` to inspect the connection.

The equivalent user configuration is:

```toml
[mcp_servers.jev-native]
url = "http://127.0.0.1:8765/mcp"
```

Codex CLI, the IDE extension, and the desktop app share the MCP configuration
on the same host. Direct MCP setup does not install the bundled skills.

### Complete plugin through the packaged local marketplace

The ready-made portable ZIP already contains a marketplace. After extraction,
its two roots are:

```text
jev-native-portable-0.4.0/       BUNDLE_ROOT
├── .agents/plugins/marketplace.json
└── plugins/
    └── jev-native/              PLUGIN_ROOT
```

Add `BUNDLE_ROOT` directly:

```bash
codex plugin marketplace add "<ABSOLUTE_BUNDLE_ROOT>"
codex plugin marketplace list
```

The source repository or a GitHub-generated source ZIP is only `PLUGIN_ROOT`;
it is not a marketplace. Maintainers can build a portable bundle from source:

```bash
python3 scripts/verify_release.py
python3 scripts/package_portable.py --output ../dist/jev-native-0.4.0.zip
python3 -m zipfile -e ../dist/jev-native-0.4.0.zip ../dist
codex plugin marketplace add "<ABSOLUTE_BUNDLE_ROOT>"
```

On Windows, run the verification and packaging steps through
`& ".\server\.venv\Scripts\python.exe"` and extract the ZIP with the platform's
archive UI or `Expand-Archive`. Do not assume a `python3` command exists.

`BUNDLE_ROOT` ends with `jev-native-portable-0.4.0` and contains
`.agents/plugins/marketplace.json`. The source repository itself is not a valid
marketplace source.

Restart the ChatGPT desktop app, open the Plugins Directory, choose **Jev Native
Portable**, and install **Jev Native**. Open a new session after installation.
The desktop app loads the installed copy from its plugin cache, not from the
source directory.

These steps follow the current
[OpenAI plugin packaging documentation](https://developers.openai.com/plugins/build/plugins).
The portable marketplace path was live-verified with Codex CLI
`0.155.0-alpha.9.2`: both bundled skills loaded and the candidate MCP server's
`jev_health` tool was discovered and called.

## Claude Code

### Complete local plugin

From `PLUGIN_ROOT`—the repository root for a source checkout, or
`BUNDLE_ROOT/plugins/jev-native` for the portable ZIP:

```bash
claude --plugin-dir "<PLUGIN_ROOT>"
```

This loads `.claude-plugin/plugin.json`, `.mcp.json`, and both bundled skills
for that session. Use `/mcp` to inspect the server. After editing the plugin,
run `/reload-plugins`; for a clean acceptance check, start a new session.

Claude documents this development path in
[Create plugins](https://code.claude.com/docs/en/plugins#test-your-plugins-locally).
Manifest validation passed. Live pickup remains unverified because the available
Claude Code `2.0.65` timed out on the same non-interactive control request both
with and without this plugin; that does not establish a plugin failure.

### Claude direct MCP connection

For tools without bundled skills:

```bash
claude mcp add --scope user --transport http jev-native http://127.0.0.1:8765/mcp
claude mcp get jev-native
claude
```

User scope makes the server available to all projects for the current account.
For one project only, change to that project's directory and use:

```bash
claude mcp add --scope local --transport http jev-native http://127.0.0.1:8765/mcp
```

Use one scope intentionally. Inspect an existing entry before adding the same
name again. Inside Claude Code, use `/mcp` to inspect status. See Anthropic's
current
[MCP documentation](https://code.claude.com/docs/en/mcp).

The configuration command writing successfully does not prove discovery or
activation. That path remains unverified for this public tree until a fresh
client session lists the tools and completes `jev_health`.

## Generic MCP clients

Configure one Streamable HTTP server named `jev-native` at the endpoint. The
equivalent JSON shape is:

```json
{
  "mcpServers": {
    "jev-native": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Client schemas differ. Confirm the installed client's current format instead
of copying this object into an unrelated settings file.

## Private server profile

The server and client must use the same explicit RFC 1918 or IPv6 ULA address.
For a source plugin artifact on macOS or Linux, update `.mcp.json` before
verification and packaging:

```bash
python3 tools/configure_profile.py --url "http://10.42.0.8:8765/mcp"
python3 tools/configure_profile.py --check
python3 scripts/verify_release.py
```

Windows PowerShell:

```powershell
& ".\server\.venv\Scripts\python.exe" tools\configure_profile.py `
  --url "http://10.42.0.8:8765/mcp"
& ".\server\.venv\Scripts\python.exe" tools\configure_profile.py --check
& ".\server\.venv\Scripts\python.exe" scripts\verify_release.py
```

Replace the example with the server's assigned private address. A changed
`.mcp.json` creates a different artifact; rebuild the archive and checksum.
Direct MCP users should enter the same reviewed URL in their client rather than
editing a verified archive.

## Acceptance check

In a new client session:

1. Confirm all eight `jev_*` tools are present.
2. For a complete-plugin route, confirm both bundled skills. Claude Code names
   them `/jev-native:jev-native` and `/jev-native:jev-pentest`.
3. Call `jev_health` without making a decision call.
4. Verify the server, contract, backend, model, data classes, fallback state,
   and live limits listed in [deployment.md](deployment.md).
5. Optionally run the README's tiny synthetic ranking as a paid end-to-end
   provider and receipt smoke.
6. Keep the integration disabled if discovery, approval, health, or structured
   output fails.

The TypeSafe and receipt HMAC secrets stay on the server. Never place them in
`.mcp.json`, Codex configuration, Claude configuration, plugin manifests,
prompts, or release archives.
