from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memlite.evaluation.comparison_benchmark import STRATEGIES, _select_history, run_comparisons
from memlite.evaluation.datasets import BenchmarkSequence
from memlite.evaluation.run_log import RunLogStore


class ComparisonBenchmarkTestCase(unittest.TestCase):
    def test_comparison_benchmark_writes_all_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)

            report = run_comparisons(
                Path("experiments/datasets/mvp.json"),
                output_directory,
            )

            self.assertEqual(len(report["strategy_comparison"]), 7)
            self.assertEqual(len(report["token_budget_comparison"]), 6)
            self.assertEqual(len(report["corpus_latency_comparison"]), 5)
            for name in (
                "comparison.json",
                "strategy_comparison.csv",
                "token_budget_comparison.csv",
                "corpus_latency_comparison.csv",
                "environment.json",
                "summary.md",
                "runs.db",
            ):
                self.assertTrue((output_directory / name).is_file())
            parsed = json.loads((output_directory / "comparison.json").read_text("utf-8"))
            self.assertEqual(parsed["dataset_sequences"], 31)
            with RunLogStore(output_directory / "runs.db") as log:
                runs = log.list_runs(report["experiment_id"])
                self.assertEqual(len(runs), 13)
                self.assertTrue(all(run.status == "completed" for run in runs))
                hybrid = next(run for run in runs if run.strategy == "hybrid_top5")
                self.assertTrue(log.list_retrieval_events(hybrid.id))
                self.assertTrue(log.list_metrics(hybrid.id))

    def test_history_baselines_preserve_replaced_facts_and_apply_window(self) -> None:
        memories = [
            {"key": "old", "content": "Database SQLite", "type": "semantic"},
            {"key": "new", "content": "Database MySQL", "type": "semantic", "supersedes": "old"},
            *[
                {"key": f"noise-{i}", "content": f"Event {i}", "type": "episodic"}
                for i in range(10)
            ],
            {"key": "private", "content": "Secret", "type": "semantic", "scope": "other"},
        ]
        sequence = BenchmarkSequence("demo", "update", "Test history", memories, [])
        full, _ = _select_history(sequence, STRATEGIES[0], "demo")
        recent, _ = _select_history(sequence, STRATEGIES[1], "demo")
        self.assertIn("old", full)
        self.assertIn("new", full)
        self.assertNotIn("private", full)
        self.assertEqual(recent, [f"noise-{i}" for i in range(10)])


if __name__ == "__main__":
    unittest.main()
