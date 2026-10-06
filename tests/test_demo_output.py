from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from memlite.demo import TASK_SEQUENCE

ROOT = Path(__file__).resolve().parents[1]


class DemoOutputTests(unittest.TestCase):
    def test_export_is_utf8_complete_and_does_not_silently_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "demo.txt"
            command = [sys.executable, "-m", "memlite.demo", "--output", str(output)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = output.read_bytes().decode("utf-8")
            self.assertNotIn("\ufffd", text)
            for task in TASK_SEQUENCE:
                self.assertIn(task["task"], text)
            self.assertIn("[fake-response]", text)
            self.assertIn("Demo completed.", text)
            self.assertNotIn(str(Path(temporary).parent), text)
            original = output.read_bytes()
            result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), original)
