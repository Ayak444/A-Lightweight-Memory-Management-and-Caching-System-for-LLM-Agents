from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memlite.evaluation.challenge_benchmark import (
    evaluate_case,
    make_challenge_dataset,
    validate_dataset,
)
from memlite.evaluation.protection_benchmark import (
    PROTECTION_STRATEGIES,
    make_protection_dataset,
    run_protection_benchmark,
)


class ProtectionBenchmarkTests(unittest.TestCase):
    def test_new_dataset_preserves_original_cases_and_declares_negative_metadata_cases(
        self,
    ) -> None:
        original, extended = make_challenge_dataset(), make_protection_dataset()
        validate_dataset(extended)
        self.assertEqual(extended["cases"][:12], original["cases"])
        self.assertEqual(len(extended["cases"]), 22)
        self.assertFalse(extended["protection_rule"]["truth_verification"])
        self.assertEqual(extended["protection_rule"]["protected_slots"], 1)

    def test_cold_important_help_and_false_important_harm_are_both_measured(self) -> None:
        dataset = make_protection_dataset()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for category, improves in (("cold_important", True), ("important_poison", False)):
                case = next(
                    case for case in dataset["cases"] if case["id"] == f"evaluation-{category}"
                )
                before = evaluate_case(
                    case, PROTECTION_STRATEGIES[1], root / f"{category}-before.db"
                )
                after = evaluate_case(case, PROTECTION_STRATEGIES[2], root / f"{category}-after.db")
                with self.subTest(category=category):
                    self.assertEqual(after["pass"], improves)
                    self.assertNotEqual(before["pass"], after["pass"])
                    self.assertFalse(after["capacity_overflow"])
                    if improves:
                        self.assertEqual(after["expected_retention"], 1.0)
                    else:
                        self.assertEqual(after["protected_forbidden_count"], 1)
                        self.assertTrue(after["forbidden_hit"])

    def test_three_repeats_keep_harms_in_report_and_preserve_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = make_protection_dataset()
            dataset["cases"] = [
                case
                for case in dataset["cases"]
                if case["id"] in {"evaluation-cold_important", "evaluation-important_poison"}
            ]
            path = root / "dataset.json"
            path.write_text(json.dumps(dataset), encoding="utf-8")
            report = run_protection_benchmark(path, root / "output")
            self.assertEqual(report["trace_count"], 78)
            self.assertTrue(report["repeat_selection_stable"])
            self.assertEqual(report["capacity_violations"], [])
            self.assertEqual(len(report["improved_queries"]), 18)
            # Capacity 8 already retains every poison-case row in both conditions.
            self.assertEqual(len(report["regressed_queries"]), 12)
            self.assertTrue(
                all("cap8" not in row["strategy"] for row in report["regressed_queries"])
            )
            self.assertEqual(len(report["protected_pollution"]), 18)
            self.assertIsNone(report["historical_baselines_match"])
            self.assertTrue((root / "output/protection_pairs.csv").exists())
            with self.assertRaises(FileExistsError):
                run_protection_benchmark(path, root / "output")

    def test_rule_changes_fail_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = make_protection_dataset()
            dataset["protection_rule"]["importance_threshold"] = 0.1
            path = root / "dataset.json"
            path.write_text(json.dumps(dataset), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_protection_benchmark(path, root / "output")
            self.assertFalse((root / "output").exists())
