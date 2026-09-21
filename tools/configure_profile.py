#!/usr/bin/env python3
"""Validate and set the private Jev MCP endpoint in .mcp.json."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / ".mcp.json"
PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)


def _is_private_or_loopback(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_loopback or any(address in network for network in PRIVATE_NETWORKS)


def validate_mcp_url(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("MCP URL must be a non-empty URL without surrounding whitespace")

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("MCP URL is malformed") from exc

    if parsed.scheme != "http":
        raise ValueError("MCP URL must use http for the included private server")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("MCP URL must not contain credentials")
    if not hostname:
        raise ValueError("MCP URL must include an explicit IP address")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as exc:
        raise ValueError("MCP URL host must be an explicit IP address") from exc
    if address.is_unspecified or not _is_private_or_loopback(address):
        raise ValueError("MCP URL host must be loopback or an RFC 1918/ULA private address")
    if port is None or not 1 <= port <= 65_535:
        raise ValueError("MCP URL must include a port from 1 through 65535")
    if parsed.path != "/mcp" or parsed.query or parsed.fragment:
        raise ValueError("MCP URL must use the exact /mcp path without query or fragment")

    host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return f"http://{host}:{port}/mcp"


def load_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("refusing to update a symlinked MCP manifest")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"MCP manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"MCP manifest is not valid JSON: {path}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("MCP manifest root must be an object")
    servers = manifest.get("mcpServers")
    entry = servers.get("jev-native") if isinstance(servers, dict) else None
    if not isinstance(entry, dict) or entry.get("type") != "http":
        raise ValueError("MCP manifest must contain the jev-native HTTP server entry")
    return manifest


def current_url(path: Path = DEFAULT_MANIFEST) -> str:
    manifest = load_manifest(path)
    value = manifest["mcpServers"]["jev-native"].get("url")
    if not isinstance(value, str):
        raise ValueError("jev-native MCP URL is missing")
    return validate_mcp_url(value)


def configure(path: Path, url: str) -> str:
    normalized = validate_mcp_url(url)
    manifest = load_manifest(path)
    manifest["mcpServers"]["jev-native"]["url"] = normalized
    data = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"

    mode = stat.S_IMODE(path.stat().st_mode)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="MCP manifest to inspect or update (default: repository .mcp.json)",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--url", help="Exact loopback or private-IP URL ending in /mcp")
    action.add_argument("--check", action="store_true", help="Validate the current URL without writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = args.manifest.expanduser()
    try:
        if manifest.is_symlink():
            raise ValueError("refusing to update a symlinked MCP manifest")
        manifest = manifest.absolute()
        url = current_url(manifest) if args.check else configure(manifest, args.url)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "manifest": str(manifest), "mcp_url": url}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
