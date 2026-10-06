"""Fixed-rule importance protection and deliberately mislabeled-memory stress tests."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from memlite.evaluation.challenge_benchmark import (
    ResearchStrategy,
    make_challenge_dataset,
    run_challenge_benchmark,
)

PROTECTION_RULE = {
    "importance_threshold": 0.8,
    "confidence_threshold": 0.8,
    "protected_slots": 1,
    "tie_break": "importance descending, confidence descending, memory id ascending",
    "truth_verification": False,
}
PROTECTION_STRATEGIES = (
    ResearchStrategy("hybrid_top3"),
    *(
        ResearchStrategy(
            f"{'protected_' if protected else ''}{policy}_cap{capacity}_top3",
            eviction=policy,
            capacity=capacity,
            protect_important=protected,
        )
        for capacity in (2, 4, 8)
        for policy in ("lru", "lfu")
        for protected in (False, True)
    ),
)


def make_protection_dataset() -> dict[str, Any]:
    dataset = make_challenge_dataset()
    dataset["version"] = "protection-1.0.0"
    dataset["protection_rule"] = dict(PROTECTION_RULE)
    dataset["provenance"] = (
        "12 unchanged challenge cases plus 10 authored metadata-reliability stress cases; "
        "not real users or independent held-out data."
    )
    for split, project in (("development", "atlas"), ("evaluation", "beacon")):

        def memory(
            key: str, content: str, *, _project: str = project, **values: Any
        ) -> dict[str, Any]:
            return {"key": key, "content": f"{_project} {content}", **values}

        def add(
            category: str,
            query: str,
            memories: list[dict[str, Any]],
            expected: list[str],
            forbidden: list[str] | None = None,
            *,
            _split: str = split,
            _project: str = project,
        ) -> None:
            dataset["cases"].append(
                {
                    "id": f"{_split}-{category}",
                    "split": _split,
                    "category": category,
                    "query": f"{_project} {query}",
                    "memories": memories,
                    "expected": expected,
                    "forbidden": forbidden or [],
                }
            )

        for category, confidence in (("important_poison", 1.0), ("low_confidence_poison", 0.2)):
            add(
                category,
                "deployment database configuration",
                [
                    memory(
                        "wrong",
                        "deployment database configuration mysql obsolete",
                        importance=1.0,
                        confidence=confidence,
                        age_days=90,
                        access_age_days=90,
                        access_count=0,
                    ),
                    *[
                        memory(
                            f"noise-{i}",
                            f"daily meeting lunch {i}",
                            access_age_days=0,
                            access_count=10,
                        )
                        for i in range(5)
                    ],
                    memory(
                        "correct",
                        "deployment database configuration sqlite",
                        access_age_days=0,
                        access_count=20,
                    ),
                ],
                ["correct"],
                ["wrong"],
            )
        add(
            "protected_overflow",
            "emergency recovery region database runtime",
            [
                *[
                    memory(
                        key,
                        f"emergency recovery {text}",
                        importance=1.0,
                        age_days=90,
                        access_age_days=90,
                        access_count=0,
                    )
                    for key, text in (
                        ("region", "region tokyo"),
                        ("database", "database sqlite"),
                        ("runtime", "runtime python"),
                    )
                ],
                *[
                    memory(
                        f"noise-{i}", f"daily meeting lunch {i}", access_age_days=0, access_count=20
                    )
                    for i in range(6)
                ],
            ],
            ["region", "database", "runtime"],
        )
        add(
            "ordinary_rare",
            "emergency recovery key",
            [
                memory(
                    "recovery",
                    "emergency recovery key vault",
                    importance=0.5,
                    age_days=90,
                    access_age_days=90,
                    access_count=0,
                ),
                *[
                    memory(
                        f"noise-{i}", f"daily meeting lunch {i}", access_age_days=0, access_count=20
                    )
                    for i in range(10)
                ],
            ],
            ["recovery"],
        )
        add(
            "expired_important",
            "deployment database configuration",
            [
                memory(
                    "wrong",
                    "deployment database configuration mysql obsolete",
                    importance=1.0,
                    expired=True,
                    age_days=90,
                ),
                memory("correct", "deployment database configuration sqlite"),
            ],
            ["correct"],
            ["wrong"],
        )
    return dataset


def run_protection_benchmark(
    dataset_path: str | Path,
    output_directory: str | Path,
    *,
    repeats: int = 3,
    reference_directory: str | Path | None = None,
) -> dict[str, Any]:
    dataset_path, output = Path(dataset_path), Path(output_directory)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if (
        dataset.get("version") != "protection-1.0.0"
        or dataset.get("protection_rule") != PROTECTION_RULE
    ):
        raise ValueError("dataset must use the predeclared protection-1.0.0 rule")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("choose an empty/new output directory")
    report = run_challenge_benchmark(
        dataset_path,
        output,
        repeats=repeats,
        strategies=PROTECTION_STRATEGIES,
    )
    traces: list[dict[str, Any]] = json.loads(
        (output / "query_traces.json").read_text(encoding="utf-8")
    )
    by_key = {(row["strategy"], row["case_id"], row["repeat"]): row for row in traces}
    pairs: list[dict[str, Any]] = []
    for row in traces:
        if not row["strategy"].startswith("protected_"):
            continue
        baseline_name = row["strategy"].removeprefix("protected_")
        before = by_key[(baseline_name, row["case_id"], row["repeat"])]
        pairs.append(
            {
                "strategy": row["strategy"],
                "baseline": baseline_name,
                "case_id": row["case_id"],
                "category": row["category"],
                "split": row["split"],
                "repeat": row["repeat"],
                "before_pass": before["pass"],
                "after_pass": row["pass"],
                "before_expected_retention": before["expected_retention"],
                "after_expected_retention": row["expected_retention"],
                "before_selected": before["selected"],
                "after_selected": row["selected"],
                "protected": row["protected"],
                "protected_forbidden_count": row["protected_forbidden_count"],
            }
        )
    historical_match = None
    checked = 0
    if reference_directory is not None:
        reference = Path(reference_directory)
        reference_dataset = json.loads(
            (reference / "dataset_snapshot.json").read_text(encoding="utf-8")
        )
        original_cases = {case["id"]: case for case in reference_dataset["cases"]}
        current_cases = {case["id"]: case for case in dataset["cases"]}
        previous = {
            (row["strategy"], row["case_id"], row["repeat"]): row
            for row in json.loads((reference / "query_traces.json").read_text(encoding="utf-8"))
        }
        rows = [
            row
            for row in traces
            if row["case_id"] in original_cases and not row["strategy"].startswith("protected_")
        ]
        checked = len(rows)
        historical_match = (
            bool(rows)
            and all(current_cases.get(key) == value for key, value in original_cases.items())
            and all(
                (prior := previous.get((row["strategy"], row["case_id"], row["repeat"])))
                is not None
                and prior["selected"] == row["selected"]
                and prior["evicted"] == row["evicted"]
                for row in rows
            )
        )
    summary = {
        "dataset_sha256": report["dataset_sha256"],
        "rule": PROTECTION_RULE,
        "case_count": report["case_count"],
        "strategy_count": len(PROTECTION_STRATEGIES),
        "repeats": repeats,
        "trace_count": len(traces),
        "repeat_selection_stable": report["repeat_selection_stable"],
        "historical_baselines_match": historical_match,
        "historical_checked_queries": checked,
        "capacity_violations": [row for row in traces if row["capacity_overflow"]],
        "improved_queries": [row for row in pairs if not row["before_pass"] and row["after_pass"]],
        "regressed_queries": [row for row in pairs if row["before_pass"] and not row["after_pass"]],
        "protected_pollution": [row for row in pairs if row["protected_forbidden_count"] > 0],
        "pairs": pairs,
        "notes": [
            "Importance/confidence are caller ratings, not truth or evidence verification.",
            "One slot stays within capacity; eligible records beyond quota are not all pinned.",
            "No result-based tuning of retrieval weights, thresholds, budget or metadata labels.",
            "A reserved record is not necessarily one saved from actual eviction.",
            "Repeated-query counts are not independent cases; negative outcomes are retained.",
        ],
    }
    (output / "protection_comparison.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    with (output / "protection_pairs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pairs[0]))
        writer.writeheader()
        writer.writerows(pairs)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=Path("experiments/datasets/protection.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--create-dataset", action="store_true")
    args = parser.parse_args()
    if args.create_dataset:
        if args.dataset.exists():
            raise FileExistsError("refusing to overwrite an existing dataset")
        args.dataset.parent.mkdir(parents=True, exist_ok=True)
        args.dataset.write_text(
            json.dumps(make_protection_dataset(), indent=2) + "\n", encoding="utf-8"
        )
    report = run_protection_benchmark(
        args.dataset, args.output, repeats=args.repeats, reference_directory=args.reference
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "traces": report["trace_count"],
                "improved": len(report["improved_queries"]),
                "regressed": len(report["regressed_queries"]),
                "capacity_violations": len(report["capacity_violations"]),
                "historical_baselines_match": report["historical_baselines_match"],
            }
        )
    )


if __name__ == "__main__":
    main()
