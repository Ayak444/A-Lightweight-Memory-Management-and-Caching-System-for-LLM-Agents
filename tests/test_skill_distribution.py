from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from experiments.package_skill import ROOT, SKILL_PATH, build_skill_archive
from experiments.smoke_installed_skill import verify_installed_skill
from memlite.skill_cli import execute_request


class SkillDistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_archive_is_reproducible_and_manifest_verifies_payload(self) -> None:
        first = self.directory / "first.zip"
        second = self.directory / "second.zip"
        report = build_skill_archive(first)
        build_skill_archive(second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(report["sha256"], hashlib.sha256(first.read_bytes()).hexdigest())
        with zipfile.ZipFile(first) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(set(archive.namelist()), {*manifest["files"], "manifest.json"})
            for name, checksum in manifest["files"].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), checksum)
                self.assertFalse(name.startswith(("data/", ".env", "memlite/")))
                self.assertNotIn("..", Path(name).parts)
            self.assertIn("memlite-agent/SKILL.md", archive.namelist())
            self.assertIn("memlite-agent/assets/requests/remember.json", archive.namelist())

    def test_extracted_skill_runs_from_unrelated_directory(self) -> None:
        output = self.directory / "skill.zip"
        build_skill_archive(output)
        extracted = self.directory / "extracted"
        with zipfile.ZipFile(output) as archive:
            archive.extractall(extracted)
        skill = extracted / "memlite-agent"
        database = self.directory / "demo.db"
        for operation in ("remember", "retrieve", "list"):
            result = subprocess.run(
                [
                    sys.executable,
                    str(skill / "scripts/memory_tool.py"),
                    "--repo",
                    str(ROOT),
                    "--db",
                    str(database),
                    "--request-file",
                    str(skill / f"assets/requests/{operation}.json"),
                ],
                cwd=self.directory,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            response = json.loads(result.stdout)
            self.assertTrue(response["ok"])
            if operation == "remember":
                memory_id = response["result"]["memory"]["id"]
            elif operation == "retrieve":
                self.assertEqual(response["result"]["selected_memory_ids"], [memory_id])
            else:
                self.assertEqual(len(response["result"]["memories"]), 1)
        self.assertEqual(
            execute_request(database, {"operation": "list", "scope": "project:other"}),
            {"memories": []},
        )

    def fixture_root(self) -> Path:
        root = self.directory / "source"
        shutil.copytree(ROOT / SKILL_PATH, root / SKILL_PATH)
        shutil.copy2(ROOT / "LICENSE", root / "LICENSE")
        shutil.copy2(ROOT / "docs/SKILL_INSTALL.zh-TW.md", root / "docs/SKILL_INSTALL.zh-TW.md")
        return root

    def test_missing_required_file_fails_before_creating_archive(self) -> None:
        root = self.fixture_root()
        (root / SKILL_PATH / "SKILL.md").unlink()
        output = self.directory / "missing.zip"
        with self.assertRaisesRegex(ValueError, "missing skill file"):
            build_skill_archive(output, root=root)
        self.assertFalse(output.exists())

    def test_unexpected_database_is_not_packaged(self) -> None:
        root = self.fixture_root()
        (root / SKILL_PATH / "private.db").write_bytes(b"private test fixture")
        output = self.directory / "unsafe.zip"
        with self.assertRaisesRegex(ValueError, "unexpected skill asset"):
            build_skill_archive(output, root=root)
        self.assertFalse(output.exists())

    def test_existing_archive_is_not_overwritten(self) -> None:
        output = self.directory / "existing.zip"
        output.write_bytes(b"keep this archive")
        with self.assertRaises(FileExistsError):
            build_skill_archive(output)
        self.assertEqual(output.read_bytes(), b"keep this archive")

    def test_helper_missing_runtime_fails_without_creating_database(self) -> None:
        database = self.directory / "untouched.db"
        helper = ROOT / SKILL_PATH / "scripts/memory_tool.py"
        result = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--repo",
                str(self.directory),
                "--db",
                str(database),
                "--request-file",
                str(ROOT / SKILL_PATH / "assets/requests/list.json"),
            ],
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"specify a MemLite checkout", result.stderr)
        self.assertFalse(database.exists())

    def test_install_smoke_verifies_copied_assets_and_operations(self) -> None:
        skill = self.directory / "installed"
        shutil.copytree(ROOT / SKILL_PATH, skill)
        report = verify_installed_skill(skill)
        self.assertEqual(report["verified_files"], 8)
        self.assertEqual(report["operations"], 3)
        self.assertEqual(report["remote_calls"], 0)
        (skill / "SKILL.md").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed installed skill file"):
            verify_installed_skill(skill)
