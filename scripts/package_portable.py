#!/usr/bin/env python3
"""Build an inventory-bounded, deterministic portable Jev plugin archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RELEASE_INVENTORY_NAME = "release-files.txt"
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "env",
    "htmlcov",
    "runtime",
    "venv",
}
EXCLUDED_PARTS = {
    ("server", "evals", "results"),
}
EXCLUDED_NAMES = {
    ".DS_Store",
    ".coverage",
    ".env",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "usage.json",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".swp"}
SECRET_PATTERNS = {
    "private-key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+"
        rb"[A-Za-z0-9+/=\r\n]{40,}-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "typesafe-key-assignment": re.compile(
        rb"(?i)TYPESAFE(?:_AI)?_API_KEY\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"
    ),
    "receipt-hmac-key-assignment": re.compile(
        rb"(?i)JEV_RECEIPT_HMAC_KEY\s*[:=]\s*['\"]?[A-Za-z0-9_~+/=\-]{32,}"
    ),
}
BEARER_PATTERN = re.compile(
    rb"(?i)Authorization\s*:\s*Bearer\s+([A-Za-z0-9._~+/=-]{24,})"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plugin_version(plugin_root: Path = PLUGIN_ROOT) -> str:
    manifest = json.loads(
        (plugin_root / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    value = manifest.get("version")
    if not isinstance(value, str) or not value:
        raise ValueError(".claude-plugin/plugin.json has no non-empty version")
    return value


def is_excluded(path: Path, plugin_root: Path = PLUGIN_ROOT) -> bool:
    relative = path.relative_to(plugin_root)
    parts = relative.parts
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    if any(part.endswith(".egg-info") for part in parts):
        return True
    if any(tuple(parts[: len(prefix)]) == prefix for prefix in EXCLUDED_PARTS):
        return True
    if path.name.startswith(".env"):
        return True
    if path.name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES:
        return True
    if parts[:1] == ("dist",):
        return True
    return False


def _validate_inventory_entry(value: str, line_number: int) -> str:
    if not value or value != value.strip() or "\\" in value or "\x00" in value:
        raise RuntimeError(f"invalid release inventory path on line {line_number}")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or value == "."
        or any(part in {"", ".", ".."} or ":" in part for part in relative.parts)
    ):
        raise RuntimeError(f"unsafe release inventory path on line {line_number}: {value!r}")
    return value


def load_release_inventory(plugin_root: Path = PLUGIN_ROOT) -> list[str]:
    inventory_path = plugin_root / RELEASE_INVENTORY_NAME
    if inventory_path.is_symlink():
        raise RuntimeError("release inventory must not be a symlink")
    try:
        lines = inventory_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing release inventory: {RELEASE_INVENTORY_NAME}") from exc
    entries = [
        _validate_inventory_entry(value, line_number)
        for line_number, value in enumerate(lines, start=1)
    ]
    if len(entries) != len(set(entries)):
        raise RuntimeError("release inventory contains duplicate paths")
    if entries != sorted(entries):
        raise RuntimeError("release inventory paths must be sorted")
    if RELEASE_INVENTORY_NAME not in entries:
        raise RuntimeError("release inventory must include itself")
    return entries


def _git_tracked_files(plugin_root: Path) -> set[str] | None:
    git_marker = plugin_root / ".git"
    if not git_marker.exists() and not git_marker.is_symlink():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(plugin_root), "ls-files", "-z", "--cached", "--", "."],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("cannot validate release inventory against Git") from exc
    if result.returncode != 0:
        raise RuntimeError("git ls-files failed while validating release inventory")
    try:
        return {
            raw.decode("utf-8")
            for raw in result.stdout.split(b"\0")
            if raw
        }
    except UnicodeDecodeError as exc:
        raise RuntimeError("tracked release paths must be valid UTF-8") from exc


def _validate_git_inventory(plugin_root: Path, entries: list[str]) -> None:
    tracked = _git_tracked_files(plugin_root)
    if tracked is None:
        return
    listed = set(entries)
    # Permit the new inventory to validate before its first commit. No other
    # untracked path receives this bootstrap exception.
    if RELEASE_INVENTORY_NAME not in tracked and (plugin_root / RELEASE_INVENTORY_NAME).is_file():
        tracked.add(RELEASE_INVENTORY_NAME)
    missing = sorted(tracked - listed)
    unexpected = sorted(listed - tracked)
    if missing or unexpected:
        raise RuntimeError(
            "release inventory differs from tracked files "
            f"(missing={missing}, unexpected={unexpected})"
        )


def collect_files(plugin_root: Path = PLUGIN_ROOT) -> list[Path]:
    plugin_root = plugin_root.resolve()
    entries = load_release_inventory(plugin_root)
    _validate_git_inventory(plugin_root, entries)
    files: list[Path] = []
    for relative in entries:
        path = plugin_root
        for part in PurePosixPath(relative).parts:
            path = path / part
            if path.is_symlink():
                raise RuntimeError(f"refusing to package symlink: {relative}")
        if not path.exists():
            raise RuntimeError(f"release inventory file is missing: {relative}")
        if not path.is_file():
            raise RuntimeError(f"release inventory entry is not a regular file: {relative}")
        if is_excluded(path, plugin_root):
            raise RuntimeError(f"release inventory includes an excluded path: {relative}")
        files.append(path)
    return files


def detect_secrets(data: bytes) -> list[str]:
    labels = [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(data)]
    for match in BEARER_PATTERN.finditer(data):
        token = match.group(1)
        counts = {byte: token.count(byte) for byte in set(token)}
        entropy = -sum(
            (count / len(token)) * math.log2(count / len(token))
            for count in counts.values()
        )
        if entropy >= 3.5:
            labels.append("high-entropy-bearer-token")
    return labels


def screen_for_secrets(files: list[Path], plugin_root: Path = PLUGIN_ROOT) -> None:
    findings: list[str] = []
    for path in files:
        data = path.read_bytes()
        for label in detect_secrets(data):
            findings.append(f"{path.relative_to(plugin_root).as_posix()}: {label}")
    if findings:
        raise RuntimeError("refusing to package suspected secrets:\n" + "\n".join(findings))


def archive_entry(path: str, data: bytes, mode: int = 0o644) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(path, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = mode << 16
    return info, data


def generated_marketplace_files(version: str) -> dict[str, bytes]:
    codex = {
        "name": "jev-native-portable",
        "interface": {"displayName": "Jev Native Portable"},
        "plugins": [
            {
                "name": "jev-native",
                "source": {"source": "local", "path": "./plugins/jev-native"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }
        ],
    }
    claude = {
        "name": "jev-native-portable",
        "owner": {"name": "Jev Native contributors"},
        "description": "Traceable first-pass review of public code and documents through hosted Jev",
        "metadata": {
            "description": "Traceable first-pass review of public code and documents through hosted Jev"
        },
        "plugins": [
            {
                "name": "jev-native",
                "source": "./jev-native",
                "description": "Traceable first-pass review through a loopback or private-network MCP backed by hosted Jev",
                "version": version,
                "author": {"name": "Jev Native contributors"},
                "category": "Productivity",
            }
        ],
    }
    return {
        ".agents/plugins/marketplace.json": (
            json.dumps(codex, indent=2, sort_keys=True) + "\n"
        ).encode(),
        "plugins/.claude-plugin/marketplace.json": (
            json.dumps(claude, indent=2, sort_keys=True) + "\n"
        ).encode(),
    }


def validate_output_path(output: Path, plugin_root: Path = PLUGIN_ROOT) -> Path:
    resolved_root = plugin_root.resolve()
    resolved_output = output.expanduser().resolve()
    if resolved_output == resolved_root or resolved_root in resolved_output.parents:
        raise RuntimeError("archive output must be outside the plugin source root")
    return resolved_output


def build_archive(
    output: Path, plugin_root: Path = PLUGIN_ROOT
) -> tuple[Path, str, int]:
    plugin_root = plugin_root.resolve()
    output = validate_output_path(output, plugin_root)
    files = collect_files(plugin_root)
    screen_for_secrets(files, plugin_root)
    version = plugin_version(plugin_root)
    bundle_root = f"jev-native-portable-{version}"
    generated = generated_marketplace_files(version)
    records = [
        {"path": path, "sha256": sha256_bytes(data), "size": len(data), "generated": True}
        for path, data in sorted(generated.items())
    ]
    for path in files:
        relative = path.relative_to(plugin_root).as_posix()
        data = path.read_bytes()
        archive_path = f"plugins/jev-native/{relative}"
        records.append(
            {
                "path": archive_path,
                "sha256": sha256_bytes(data),
                "size": len(data),
                "generated": False,
            }
        )

    manifest = {
        "schema_version": 1,
        "plugin": "jev-native",
        "version": version,
        "bundle_root": bundle_root,
        "transport": "private-local-or-vpn-mcp",
        "known_secret_patterns_detected": False,
        "files": records,
    }
    manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for relative, data in sorted(generated.items()):
            info, content = archive_entry(f"{bundle_root}/{relative}", data)
            archive.writestr(info, content)
        for path in files:
            relative = path.relative_to(plugin_root).as_posix()
            mode = 0o755 if path.suffix == ".py" and path.stat().st_mode & 0o111 else 0o644
            info, data = archive_entry(
                f"{bundle_root}/plugins/jev-native/{relative}", path.read_bytes(), mode
            )
            archive.writestr(info, data)
        info, data = archive_entry(f"{bundle_root}/PACKAGE-MANIFEST.json", manifest_data)
        archive.writestr(info, data)

    digest = sha256_bytes(output.read_bytes())
    return output, digest, len(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Archive path (default: ../dist/jev-native-<version>.zip)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        version = plugin_version()
        output = args.output or PLUGIN_ROOT.parent / "dist" / f"jev-native-{version}.zip"
        output, digest, count = build_archive(output)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"package failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"archive": str(output), "sha256": digest, "files": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
