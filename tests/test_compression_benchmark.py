from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memlite.evaluation.compression_benchmark import run_compression_benchmark, validate_dataset

ROOT = Path(__file__).resolve().parents[1]


class CompressionBenchmarkTests(unittest.TestCase):
    def test_agent_prompt_evidence_records_fact_loss_and_preserves_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            report = run_compression_benchmark(
                ROOT / "experiments/datasets/compression.json", output
            )
            self.assertEqual(report["trace_count"], 108)
            self.assertTrue(report["repeat_context_stable"])
            self.assertEqual(report["budget_violations"], 0)
            self.assertEqual(report["source_mutations"], 0)
            traces = json.loads((output / "query_traces.json").read_text(encoding="utf-8"))
            self.assertTrue(
                all(row["all_facts_retained"] for row in traces if row["budget"] is None)
            )
            self.assertTrue(any(row["dropped"] for row in traces if row["budget"] == 8))
            self.assertTrue(all(row["provider_calls"] == 1 for row in traces))
            for name in (
                "compression_report.json",
                "environment.json",
                "dataset_snapshot.json",
                "compression_comparison.csv",
            ):
                self.assertTrue((output / name).is_file())
            with self.assertRaises(FileExistsError):
                run_compression_benchmark(ROOT / "experiments/datasets/compression.json", output)

    def test_invalid_labels_repeats_and_source_budget_fail_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "invalid.json"
            output = root / "output"
            dataset = {
                "version": "compression-1.0.0",
                "cases": [
                    {
                        "id": "a",
                        "query": "database",
                        "content": "SQLite database",
                        "required": ["missing"],
                    }
                ],
            }
            with self.assertRaises(ValueError):
                validate_dataset(dataset)
            dataset["cases"][0]["required"] = ["SQLite"]
            path.write_text(json.dumps(dataset), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_compression_benchmark(path, output, repeats=2)
            dataset["cases"][0]["content"] += "x" * 21000
            path.write_text(json.dumps(dataset), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "L1 budget"):
                run_compression_benchmark(path, output)
            self.assertFalse(output.exists())
