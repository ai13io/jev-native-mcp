#!/usr/bin/env python3
"""Fail-loud portable release checks that require only the Python standard library."""

from __future__ import annotations

import ipaddress
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import package_portable


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str) -> dict:
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def extract(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f"cannot find {label}")
    return match.group(1)


def main() -> int:
    try:
        codex = load_json(".codex-plugin/plugin.json")
        claude = load_json(".claude-plugin/plugin.json")
        codex_mcp = load_json(".mcp.json")

        version = claude.get("version")
        require(isinstance(version, str) and bool(version), "Claude manifest version is missing")
        require(
            str(codex.get("version", "")).split("+", 1)[0] == version,
            "Codex manifest base version differs",
        )

        pyproject = (ROOT / "server/pyproject.toml").read_text(encoding="utf-8")
        project_version = extract(
            r"^version\s*=\s*[\"']([^\"']+)[\"']", pyproject, "server project version"
        )
        require(project_version == version, "server pyproject version differs")
        require(
            'py-modules = ["server", "receipt_ledger"]' in pyproject,
            "server module discovery is not pinned",
        )
        require("[project.optional-dependencies]" in pyproject, "pip dev extra is missing")

        server_source = (ROOT / "server/server.py").read_text(encoding="utf-8")
        server_version = extract(
            r'^VERSION\s*=\s*[\"\']([^\"\']+)[\"\']', server_source, "server runtime version"
        )
        require(server_version == version, "server runtime version differs")
        for tool_name in (
            "jev_health",
            "jev_decide",
            "jev_rank",
            "jev_batch_check",
            "jev_claim_audit",
            "jev_select",
            "jev_signal_matrix",
            "jev_record_outcome",
        ):
            require(
                f"async def {tool_name}(" in server_source,
                f"server tool missing: {tool_name}",
            )

        codex_entry = codex_mcp["mcpServers"]["jev-native"]
        require(codex_entry.get("type") == "http", "Codex MCP type must be http")
        parsed = urlparse(str(codex_entry.get("url")))
        address = ipaddress.ip_address(parsed.hostname or "")
        require(parsed.scheme == "http", "private MCP transport must use explicit http")
        require(address.is_private and not address.is_unspecified, "MCP endpoint is not private")
        require(
            not (ROOT / "mcp.json").exists(),
            "root mcp.json conflicts with private non-loopback HTTP in current Codex",
        )
        require(
            not (ROOT / "plugin.json").exists(),
            "root plugin.json should not advertise the incompatible Agent Plugins layout",
        )

        required = [
            "release-files.txt",
            "skills/jev-native/SKILL.md",
            "skills/jev-pentest/SKILL.md",
            "server/server.py",
            "server/receipt_ledger.py",
            "scripts/package_portable.py",
        ]
        for relative in required:
            require((ROOT / relative).is_file(), f"required file missing: {relative}")

        for skill_name in ("jev-native", "jev-pentest"):
            agent_yaml = (ROOT / f"skills/{skill_name}/agents/openai.yaml").read_text()
            require(
                f"${skill_name}" in agent_yaml,
                f"{skill_name} default prompt does not explicitly invoke its skill",
            )

        package_portable.screen_for_secrets(package_portable.collect_files())
    except (KeyError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "plugin": codex["name"],
                "version": version,
                "mcp_url": codex_entry["url"],
                "known_secret_patterns_detected": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
