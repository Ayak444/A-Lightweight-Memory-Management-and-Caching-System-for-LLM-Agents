from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memlite.evaluation.agent_benchmark import run_agent_cache_benchmark


class AgentBenchmarkTests(unittest.TestCase):
    def test_cache_avoids_repeated_calls_without_changing_identical_task_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_agent_cache_benchmark(temporary, repeats=3)
            plain, cached = report["results"]
            self.assertEqual(plain["provider_calls"], 18)
            self.assertEqual(cached["provider_calls"], 6)
            self.assertEqual(cached["cache_hits"], 12)
            self.assertEqual(cached["output_identity_rate"], 1.0)
            self.assertLess(cached["estimated_provider_tokens"], plain["estimated_provider_tokens"])
            self.assertTrue((Path(temporary) / "agent_cache_comparison.json").exists())
