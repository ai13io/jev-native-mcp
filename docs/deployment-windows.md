# Windows deployment

The repository includes a foreground PowerShell launcher. It has not been
live-verified for this public tree, and the configured Windows CI job has not
yet run. This release does not install or configure a persistent Windows
service.

## Install

Open PowerShell and run:

```powershell
Set-Location "<PLUGIN_ROOT>"
py -3 -m venv server\.venv
& ".\server\.venv\Scripts\python.exe" -m pip install ".\server"
```

Python 3.10 or later is required.

## Start in the foreground

The launcher prompts for missing secrets with secure input and keeps them out
of its command line:

```powershell
Set-Location "<PLUGIN_ROOT>"
& ".\server\deploy\run-windows.ps1" `
  -Python ".\server\.venv\Scripts\python.exe" `
  -HostAddress "127.0.0.1" `
  -Port 8765
```

The receipt HMAC key must contain at least 32 UTF-8 bytes and remain stable
across provider-key rotation. Keep the terminal open while the server is in
use; stop it with `Control-C`.

For a remote private profile, replace `127.0.0.1` with one explicit private
VPN/LAN address assigned to this computer and allow inbound TCP only on the
intended private Windows Firewall profile. Never use `0.0.0.0`, `::`, a public
address, or a public port-forward.

## Persistence limitation

The repository intentionally includes no Windows service wrapper, scheduled
task, or unattended secret-store integration. Those choices affect account
isolation, restart behavior, and secret handling and must be reviewed for the
target environment. Do not improvise persistence by placing either secret in a
shortcut, task argument, or checked-in script.

Verify a foreground listener with:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 8765
```

Then complete the checks in [deployment.md](deployment.md) from a new client
session.

Do not mark the launcher operational until it starts on the target Windows host
and a new client session completes `jev_health`.
