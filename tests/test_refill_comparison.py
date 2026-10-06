from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.run_refill_comparison import run_refill_comparison
from memlite.evaluation.challenge_benchmark import STRATEGIES, make_challenge_dataset


class RefillComparisonTests(unittest.TestCase):
    def test_paired_fixed_inputs_recover_expired_case_without_changing_clean_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = make_challenge_dataset()
            dataset["cases"] = [
                case
                for case in dataset["cases"]
                if case["id"] in {"evaluation-expired_candidates", "evaluation-long_history"}
            ]
            path = root / "dataset.json"
            path.write_text(json.dumps(dataset), encoding="utf-8")
            report = run_refill_comparison(path, root / "output", strategies=STRATEGIES[3:5])
            self.assertEqual(report["changed_queries"], 3)
            self.assertEqual(report["regressions"], [])
            self.assertEqual(report["unexpected_changes"], [])
            self.assertTrue(report["before_repeat_stable"])
            self.assertTrue(report["after_repeat_stable"])
            self.assertIsNone(report["baseline_matches_reference"])
            self.assertTrue((root / "output/refill_comparison.csv").exists())
            before = json.loads((root / "output/no_refill/challenge_report.json").read_text())
            after = json.loads((root / "output/refill/challenge_report.json").read_text())
            self.assertEqual(before["dataset_sha256"], after["dataset_sha256"])
            self.assertEqual(before["retrieval_config"]["candidate_scan_limit"], 20)
            self.assertIsNone(after["retrieval_config"]["candidate_scan_limit"])
            # An independently saved earlier control can be checked, never overwritten.
            again = run_refill_comparison(
                path,
                root / "again",
                strategies=STRATEGIES[3:5],
                reference_directory=root / "output/no_refill",
            )
            self.assertTrue(again["baseline_matches_reference"])
            with self.assertRaises(FileExistsError):
                run_refill_comparison(path, root / "output", strategies=STRATEGIES[3:5])

    def test_at_least_three_repetitions_required_before_creating_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                run_refill_comparison(root / "missing.json", root / "output", repeats=2)
            self.assertFalse((root / "output").exists())
