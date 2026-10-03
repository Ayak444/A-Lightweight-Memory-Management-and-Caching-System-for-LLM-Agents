from __future__ import annotations

import unittest
from pathlib import Path

from memlite.evaluation.retrieval_benchmark import run_retrieval_benchmark


class RetrievalBenchmarkTestCase(unittest.TestCase):
    def test_baseline_runs_all_queries_and_returns_bounded_metrics(self) -> None:
        result = run_retrieval_benchmark(Path("experiments/datasets/mvp.json"))
        summary = result.summary()

        self.assertEqual(summary["queries"], 10)
        for metric in ("pass_rate", "mean_precision", "mean_recall", "mean_reciprocal_rank"):
            self.assertGreaterEqual(summary[metric], 0.0)
            self.assertLessEqual(summary[metric], 1.0)
        self.assertGreaterEqual(summary["latency_ms_p50"], 0.0)


if __name__ == "__main__":
    unittest.main()
