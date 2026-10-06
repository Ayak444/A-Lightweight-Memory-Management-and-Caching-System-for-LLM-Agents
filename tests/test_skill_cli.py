from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from memlite.skill_cli import execute_request

ROOT = Path(__file__).resolve().parents[1]


class SkillBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "memory.db"

    def request(self, operation: str, scope: str = "project:a", **kwargs: Any) -> dict[str, Any]:
        return execute_request(self.database, {"operation": operation, "scope": scope, **kwargs})

    def test_memory_lifecycle_and_cross_scope_operations(self) -> None:
        item = self.request("remember", content="專案使用 SQLite database")["memory"]
        memory_id = item["id"]
        response = self.request("retrieve", query="SQLite database")
        self.assertEqual(response["selected_memory_ids"], [memory_id])
        self.assertEqual(self.request("list", "project:b")["memories"], [])
        for operation in ("inspect", "supersede", "forget"):
            with self.subTest(operation=operation), self.assertRaises(LookupError):
                kwargs = {"content": "wrong"} if operation == "supersede" else {}
                self.request(operation, "project:b", memory_id=memory_id, **kwargs)
        replacement = self.request("supersede", memory_id=memory_id, content="專案改用 PostgreSQL")[
            "memory"
        ]
        self.assertNotEqual(replacement["id"], memory_id)
        self.assertEqual(
            self.request("inspect", memory_id=memory_id)["memory"]["status"], "superseded"
        )
        self.assertTrue(self.request("forget", memory_id=replacement["id"])["deleted"])
        self.assertEqual(self.request("list")["memories"], [])

    def test_inspection_does_not_touch_frequency_and_empty_type_means_no_results(self) -> None:
        item = self.request("remember", content="SQLite database")["memory"]
        self.assertEqual(self.request("list")["memories"][0]["access_count"], 0)
        self.assertEqual(self.request("inspect", memory_id=item["id"])["memory"]["access_count"], 0)
        self.assertEqual(
            self.request("retrieve", query="SQLite", types=[])["selected_memory_ids"], []
        )

    def test_invalid_values_do_not_modify_records_and_ttl_correction_preserves_expiry(self) -> None:
        for kwargs in (
            {"confidence": True},
            {"confidence": float("nan")},
            {"ttl_seconds": 1.5},
            {"ttl_seconds": 0},
            {"type": "unknown"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                self.request("remember", content="test", **kwargs)
        with self.assertRaises(ValueError):
            self.request("list", limit=1001)
        with self.assertRaises(ValueError):
            self.request("list", ttl_seconds=60)
        item = self.request("remember", content="temporary", ttl_seconds=60)["memory"]
        replacement = self.request("supersede", memory_id=item["id"], content="still temporary")[
            "memory"
        ]
        self.assertEqual(replacement["expires_at"], item["expires_at"])
        self.assertEqual(
            self.request("inspect", memory_id=item["id"])["memory"]["content"], "temporary"
        )

    def test_cli_utf8_input_and_machine_readable_errors(self) -> None:
        command = [sys.executable, "-m", "memlite.skill_cli", "--db", str(self.database)]
        request = {"operation": "remember", "scope": "測試範圍", "content": "繁體中文事實"}
        response = subprocess.run(
            command,
            input=json.dumps(request, ensure_ascii=False).encode(),
            capture_output=True,
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)["result"]["memory"]["content"], "繁體中文事實")
        response = subprocess.run(command, input=b"[]", capture_output=True, cwd=ROOT, check=False)
        self.assertEqual(response.returncode, 1)
        self.assertFalse(json.loads(response.stdout)["ok"])

    def test_portable_skill_helper_runs_against_explicit_repo_and_database(self) -> None:
        request = Path(self.temporary.name) / "request.json"
        request.write_text(
            json.dumps({"operation": "remember", "scope": "project:a", "content": "SQLite"}),
            encoding="utf-8",
        )
        helper = ROOT / "docs/skills/memlite-agent/scripts/memory_tool.py"
        response = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--repo",
                str(ROOT),
                "--db",
                str(self.database),
                "--request-file",
                str(request),
            ],
            capture_output=True,
            cwd=self.temporary.name,
            check=False,
        )
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertTrue(json.loads(response.stdout)["ok"])
        self.assertEqual(len(self.request("list")["memories"]), 1)
