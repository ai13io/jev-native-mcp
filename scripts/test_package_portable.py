#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import package_portable as package


AUTHORIZATION_PREFIX = b"Authorization:" + b" Bearer "
TYPESAFE_KEY_NAME = b"TYPESAFE_" + b"API_KEY"
RECEIPT_KEY_NAME = b"JEV_RECEIPT_" + b"HMAC_KEY"


class PortablePackageTests(unittest.TestCase):
    @staticmethod
    def _write_inventory(root: Path, entries: list[str]) -> None:
        (root / package.RELEASE_INVENTORY_NAME).write_text(
            "\n".join(sorted(entries)) + "\n",
            encoding="utf-8",
        )

    def test_runtime_ledger_paths_are_always_excluded(self) -> None:
        self.assertTrue(
            package.is_excluded(package.PLUGIN_ROOT / "server" / "runtime" / "usage.json")
        )
        self.assertTrue(package.is_excluded(package.PLUGIN_ROOT / "server" / "usage.json"))
        self.assertTrue(package.is_excluded(package.PLUGIN_ROOT / "server" / ".env.local"))

    def test_packager_refuses_included_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside_dir:
            root = Path(directory)
            outside = Path(outside_dir) / "outside.txt"
            outside.write_text("ordinary external content")
            (root / "linked.txt").symlink_to(outside)
            self._write_inventory(root, [package.RELEASE_INVENTORY_NAME, "linked.txt"])
            with self.assertRaisesRegex(RuntimeError, "refusing to package symlink"):
                package.collect_files(root)

    def test_positive_inventory_ignores_untracked_editor_env_coverage_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "kept.txt").write_text("public release content", encoding="utf-8")
            noise = [
                "notes.local.md",
                ".idea/workspace.xml",
                ".venv/lib/cache.py",
                "venv/lib/cache.py",
                "env/lib/cache.py",
                "coverage/index.html",
                ".coverage",
            ]
            for relative in noise:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("local-only", encoding="utf-8")
            self._write_inventory(root, ["kept.txt", package.RELEASE_INVENTORY_NAME])

            collected = {
                path.relative_to(root).as_posix()
                for path in package.collect_files(root)
            }

            self.assertEqual(collected, {"kept.txt", package.RELEASE_INVENTORY_NAME})

    def test_inventory_rejects_traversal_duplicates_and_missing_files(self) -> None:
        cases = [
            ([package.RELEASE_INVENTORY_NAME, "../outside.txt"], "unsafe"),
            ([package.RELEASE_INVENTORY_NAME, package.RELEASE_INVENTORY_NAME], "duplicate"),
            ([package.RELEASE_INVENTORY_NAME, "missing.txt"], "missing"),
        ]
        for entries, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._write_inventory(root, entries)
                with self.assertRaisesRegex(RuntimeError, message):
                    package.collect_files(root)

    def test_inventory_rejects_non_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "directory-entry").mkdir()
            self._write_inventory(
                root,
                ["directory-entry", package.RELEASE_INVENTORY_NAME],
            )
            with self.assertRaisesRegex(RuntimeError, "not a regular file"):
                package.collect_files(root)

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_git_checkout_rejects_tracked_drift_but_ignores_untracked_notes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "kept.txt").write_text("kept", encoding="utf-8")
            (root / "local-note.md").write_text("untracked", encoding="utf-8")
            self._write_inventory(root, ["kept.txt", package.RELEASE_INVENTORY_NAME])
            subprocess.run(
                ["git", "-C", str(root), "add", "kept.txt", package.RELEASE_INVENTORY_NAME],
                check=True,
            )
            collected = {
                path.relative_to(root).as_posix()
                for path in package.collect_files(root)
            }
            self.assertEqual(collected, {"kept.txt", package.RELEASE_INVENTORY_NAME})

            (root / "tracked-but-unlisted.txt").write_text("drift", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "tracked-but-unlisted.txt"],
                check=True,
            )
            with self.assertRaisesRegex(RuntimeError, "differs from tracked files"):
                package.collect_files(root)

    def test_secret_detector_ignores_documented_fake_fixture(self) -> None:
        self.assertEqual(
            package.detect_secrets(AUTHORIZATION_PREFIX + b"secretvalue123456789"),
            [],
        )

    def test_secret_detector_rejects_high_entropy_bearer(self) -> None:
        token = b"eyJhbGciOiJIUzI1NiJ9" + b".Abc123-XyZ987" + b".qwertyASDF1234"
        labels = package.detect_secrets(AUTHORIZATION_PREFIX + token)
        self.assertIn("high-entropy-bearer-token", labels)

    def test_secret_detector_allows_short_env_sentinel_but_rejects_realistic_key(self) -> None:
        self.assertEqual(
            package.detect_secrets(
                TYPESAFE_KEY_NAME + b"=SET_ME\n" + RECEIPT_KEY_NAME + b"=\n"
            ),
            [],
        )
        self.assertIn(
            "typesafe-key-assignment",
            package.detect_secrets(TYPESAFE_KEY_NAME + b"=abcdefghijklmnop"),
        )
        self.assertIn(
            "receipt-hmac-key-assignment",
            package.detect_secrets(
                RECEIPT_KEY_NAME + b"=Jg7vQ4mN9xKs2pLd8cRf5tYw1hUa6zBe"
            ),
        )

    def test_packager_rejects_output_inside_source_after_path_normalization(self) -> None:
        direct = package.PLUGIN_ROOT / "release.zip"
        repeated = package.PLUGIN_ROOT / "scripts" / ".." / "release.zip"
        for output in (direct, repeated):
            with self.assertRaisesRegex(RuntimeError, "outside the plugin source root"):
                package.build_archive(output)
            self.assertFalse(output.exists())

    def test_packager_can_replace_the_same_external_output_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "portable.zip"
            package.build_archive(output)
            first = output.read_bytes()
            package.build_archive(output)
            self.assertEqual(output.read_bytes(), first)

    def test_archives_are_deterministic_and_manifest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first.zip"
            second = Path(temp_dir) / "second.zip"
            package.build_archive(first)
            package.build_archive(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                bundle_root = f"jev-native-portable-{package.plugin_version()}"
                self.assertNotIn(f"{bundle_root}/plugins/jev-native/.env", names)
                self.assertFalse(any("/__pycache__/" in name for name in names))
                self.assertFalse(any("/build/" in name for name in names))
                self.assertFalse(any("/dist/" in name for name in names))
                self.assertFalse(any("/runtime/" in name for name in names))
                self.assertFalse(any(name.endswith("/usage.json") for name in names))
                self.assertFalse(any(".egg-info/" in name for name in names))
                self.assertFalse(any("/evals/results/" in name for name in names))
                self.assertIn(f"{bundle_root}/.agents/plugins/marketplace.json", names)
                self.assertIn(
                    f"{bundle_root}/plugins/.claude-plugin/marketplace.json", names
                )
                self.assertIn(
                    f"{bundle_root}/plugins/jev-native/docs/deployment.md", names
                )
                self.assertIn(
                    f"{bundle_root}/plugins/jev-native/tools/configure_profile.py", names
                )
                manifest = json.loads(archive.read(f"{bundle_root}/PACKAGE-MANIFEST.json"))
                self.assertFalse(manifest["known_secret_patterns_detected"])
                self.assertNotIn("contains_credentials", manifest)
                claude_marketplace = json.loads(
                    archive.read(
                        f"{bundle_root}/plugins/.claude-plugin/marketplace.json"
                    )
                )
                self.assertEqual(
                    claude_marketplace["owner"]["name"], "Jev Native contributors"
                )
                for record in manifest["files"]:
                    content = archive.read(f"{bundle_root}/{record['path']}")
                    self.assertEqual(hashlib.sha256(content).hexdigest(), record["sha256"])
                    self.assertEqual(len(content), record["size"])

    def test_extracted_portable_tree_can_rebuild_without_git_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            first = temp / "first.zip"
            second = temp / "second.zip"
            package.build_archive(first)
            with zipfile.ZipFile(first) as archive:
                archive.extractall(temp / "extracted")
                bundle_root = f"jev-native-portable-{package.plugin_version()}"
                extracted_plugin = temp / "extracted" / bundle_root / "plugins" / "jev-native"

            package.build_archive(second, plugin_root=extracted_plugin)

            with zipfile.ZipFile(first) as original, zipfile.ZipFile(second) as rebuilt:
                self.assertEqual(original.namelist(), rebuilt.namelist())
                for name in original.namelist():
                    self.assertEqual(original.read(name), rebuilt.read(name))


if __name__ == "__main__":
    unittest.main()
