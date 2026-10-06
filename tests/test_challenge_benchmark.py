from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memlite.evaluation.challenge_benchmark import (
    STRATEGIES,
    ResearchStrategy,
    evaluate_case,
    make_challenge_dataset,
    run_challenge_benchmark,
    validate_dataset,
)


class ChallengeBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = make_challenge_dataset()

    def _case(self, category: str) -> dict:
        return next(case for case in self.dataset["cases"] if case["category"] == category)

    def test_long_history_and_multiple_required_facts_expose_baseline_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            full = evaluate_case(self._case("long_history"), STRATEGIES[0], root / "full.db")
            recent = evaluate_case(self._case("long_history"), STRATEGIES[1], root / "recent.db")
            top1 = evaluate_case(self._case("three_required"), STRATEGIES[2], root / "one.db")
            self.assertTrue(full["pass"])
            self.assertFalse(recent["pass"])
            self.assertNotIn("region", recent["selected"])
            self.assertFalse(top1["pass"])
            self.assertLessEqual(top1["recall"], 1 / 3)

    def test_recent_and_frequent_pollution_can_survive_eviction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for policy in ("lru", "lfu"):
                with self.subTest(policy=policy):
                    result = evaluate_case(
                        self._case("hot_pollution"),
                        ResearchStrategy(policy, eviction=policy, capacity=2),
                        root / f"{policy}.db",
                    )
                    self.assertIn("correct", result["evicted"])
                    self.assertTrue(result["forbidden_hit"])
                    self.assertEqual(result["remaining_active"], 2)

    def test_ttl_removes_expired_index_candidates_without_changing_valid_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plain = evaluate_case(
                self._case("expired_candidates"), STRATEGIES[3], root / "plain.db"
            )
            ttl = evaluate_case(self._case("expired_candidates"), STRATEGIES[4], root / "ttl.db")
            self.assertEqual(plain["remaining_expired"], 25)
            self.assertEqual(ttl["remaining_expired"], 0)
            self.assertEqual(ttl["evicted_count"], 25)
            self.assertEqual(ttl["remaining_active"], 1)
            self.assertTrue(ttl["pass"])

    def test_repeatability_and_evidence_files_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.dataset["cases"] = [self._case("long_history"), self._case("three_required")]
            path = root / "dataset.json"
            path.write_text(json.dumps(self.dataset), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_challenge_benchmark(path, root / "short", repeats=2)
            report = run_challenge_benchmark(path, root / "output", strategies=STRATEGIES[:3])
            self.assertTrue(report["repeat_selection_stable"])
            self.assertEqual(report["repeats"], 3)
            self.assertEqual(report["case_count"], 2)
            self.assertEqual(len(report["dataset_sha256"]), 64)
            self.assertIn("memlite/engine.py", report["source_sha256"])
            self.assertEqual(
                (root / "output/dataset_snapshot.json").read_bytes(), path.read_bytes()
            )
            self.assertTrue((root / "output/environment.json").exists())
            self.assertTrue((root / "output/query_traces.json").exists())
            with self.assertRaises(FileExistsError):
                run_challenge_benchmark(path, root / "output", strategies=STRATEGIES[:3])

    def test_dataset_label_and_split_validation(self) -> None:
        validate_dataset(self.dataset)
        development = {
            case["id"] for case in self.dataset["cases"] if case["split"] == "development"
        }
        evaluation = {case["id"] for case in self.dataset["cases"] if case["split"] == "evaluation"}
        self.assertFalse(development & evaluation)
        self.dataset["cases"][0]["forbidden"] = ["region"]
        with self.assertRaises(ValueError):
            validate_dataset(self.dataset)

    def test_invalid_strategy_is_not_silently_replaced_with_lfu(self) -> None:
        with self.assertRaises(ValueError):
            ResearchStrategy("typo", eviction="lur", capacity=2)
