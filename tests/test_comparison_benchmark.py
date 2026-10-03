from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memlite.evaluation.comparison_benchmark import run_comparisons


class ComparisonBenchmarkTestCase(unittest.TestCase):
    def test_comparison_benchmark_writes_all_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)

            report = run_comparisons(
                Path("experiments/datasets/mvp.json"),
                output_directory,
            )

            self.assertEqual(len(report["strategy_comparison"]), 5)
            self.assertEqual(len(report["token_budget_comparison"]), 6)
            self.assertEqual(len(report["corpus_latency_comparison"]), 5)
            for name in (
                "comparison.json",
                "strategy_comparison.csv",
                "token_budget_comparison.csv",
                "corpus_latency_comparison.csv",
            ):
                self.assertTrue((output_directory / name).is_file())
            parsed = json.loads((output_directory / "comparison.json").read_text("utf-8"))
            self.assertEqual(parsed["dataset_sequences"], 10)


if __name__ == "__main__":
    unittest.main()
