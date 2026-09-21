from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

import configure_profile


def _manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "jev-native": {
                        "type": "http",
                        "url": "http://127.0.0.1:8765/mcp",
                        "note": "preserve me",
                    }
                },
                "unrelated": {"preserved": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://127.0.0.1:8765/mcp", "http://127.0.0.1:8765/mcp"),
        ("http://10.42.0.8:9443/mcp", "http://10.42.0.8:9443/mcp"),
        ("http://[fd00:0:0::8]:8765/mcp", "http://[fd00::8]:8765/mcp"),
    ],
)
def test_validate_mcp_url_accepts_only_explicit_local_or_private_profiles(
    value: str, expected: str
) -> None:
    assert configure_profile.validate_mcp_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://0.0.0.0:8765/mcp",
        "http://8.8.8.8:8765/mcp",
        "http://169.254.10.20:8765/mcp",
        "http://mcp.example.test:8765/mcp",
        "http://user:password@10.42.0.8:8765/mcp",
        "https://10.42.0.8:8765/mcp",
        "http://10.42.0.8/mcp",
        "http://10.42.0.8:8765/other",
        "http://10.42.0.8:8765/mcp?token=value",
        " http://127.0.0.1:8765/mcp",
    ],
)
def test_validate_mcp_url_rejects_unsafe_or_ambiguous_profiles(value: str) -> None:
    with pytest.raises(ValueError):
        configure_profile.validate_mcp_url(value)


def test_configure_updates_only_the_url_and_preserves_file_mode(tmp_path: Path) -> None:
    path = tmp_path / ".mcp.json"
    _manifest(path)
    path.chmod(0o640)

    result = configure_profile.configure(path, "http://192.168.50.7:8765/mcp")

    assert result == "http://192.168.50.7:8765/mcp"
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["mcpServers"]["jev-native"] == {
        "type": "http",
        "url": result,
        "note": "preserve me",
    }
    assert updated["unrelated"] == {"preserved": True}
    assert path.stat().st_mode & 0o777 == 0o640
    assert not list(tmp_path.glob(".*.tmp"))


def test_configure_refuses_symlinked_or_unexpected_manifests(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    _manifest(target)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlinked"):
        configure_profile.configure(link, "http://127.0.0.1:8765/mcp")

    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"mcpServers": {}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="jev-native HTTP"):
        configure_profile.configure(invalid, "http://127.0.0.1:8765/mcp")


def test_cli_rejects_manifest_symlink_before_path_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "target.json"
    _manifest(target)
    original = target.read_bytes()
    link = tmp_path / "profile-link.json"
    link.symlink_to(target)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_profile.py",
            "--manifest",
            str(link),
            "--url",
            "http://192.168.50.8:8765/mcp",
        ],
    )

    assert configure_profile.main() == 1
    assert "symlinked" in capsys.readouterr().out
    assert target.read_bytes() == original
