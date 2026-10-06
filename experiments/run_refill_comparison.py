"""Compare the original candidate boundary with metadata-aware bounded refill."""

from __future__ import annotations

import argparse
import csv
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from memlite.evaluation.challenge_benchmark import (
    STRATEGIES,
    ResearchStrategy,
    run_challenge_benchmark,
)


def _load_traces(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _key(row: dict[str, Any]) -> tuple[str, str, int]:
    return row["strategy"], row["case_id"], row["repeat"]


def run_refill_comparison(
    dataset: str | Path,
    output_directory: str | Path,
    *,
    repeats: int = 3,
    strategies: tuple[ResearchStrategy, ...] = STRATEGIES,
    reference_directory: str | Path | None = None,
) -> dict[str, Any]:
    output = Path(output_directory)
    if repeats < 3:
        raise ValueError("comparison requires at least three repetitions")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("choose an empty/new comparison directory")
    output.mkdir(parents=True, exist_ok=True)
    reference_report: dict[str, Any] | None = None
    reference: dict[tuple[str, str, int], dict[str, Any]] | None = None
    if reference_directory is not None:
        reference_root = Path(reference_directory)
        reference_report = json.loads(
            (reference_root / "challenge_report.json").read_text(encoding="utf-8")
        )
        reference = {_key(row): row for row in _load_traces(reference_root / "query_traces.json")}
    before = run_challenge_benchmark(
        dataset,
        output / "no_refill",
        repeats=repeats,
        strategies=strategies,
        candidate_scan_limit=20,
    )
    after = run_challenge_benchmark(
        dataset, output / "refill", repeats=repeats, strategies=strategies
    )
    original = {_key(row): row for row in _load_traces(output / "no_refill/query_traces.json")}
    updated = {_key(row): row for row in _load_traces(output / "refill/query_traces.json")}
    if (
        original.keys() != updated.keys()
        or before["dataset_sha256"] != after["dataset_sha256"]
        or before["source_sha256"] != after["source_sha256"]
    ):
        raise ValueError("comparison inputs differ")
    changes = [
        {
            "strategy": old["strategy"],
            "case_id": old["case_id"],
            "category": old["category"],
            "repeat": old["repeat"],
            "before_selected": old["selected"],
            "after_selected": new["selected"],
            "before_pass": old["pass"],
            "after_pass": new["pass"],
            "eviction_changed": old["evicted"] != new["evicted"],
        }
        for key, old in original.items()
        if (new := updated[key])["selected"] != old["selected"] or new["evicted"] != old["evicted"]
    ]
    metrics = (
        "pass",
        "precision",
        "recall",
        "pollution_fraction",
        "selected_tokens",
        "retrieval_ms",
        "search_rounds",
        "scanned_hits",
        "scan_limit_reached",
    )
    before_results = {(row["split"], row["strategy"]): row for row in before["results"]}
    comparisons: list[dict[str, Any]] = []
    for new in after["results"]:
        old = before_results[(new["split"], new["strategy"])]
        comparisons.append(
            {"split": new["split"], "strategy": new["strategy"]}
            | {
                f"{phase}_{metric}": row[f"mean_{metric}"]
                for phase, row in (("before", old), ("after", new))
                for metric in metrics
            }
        )
    baseline_matches_reference = None
    if reference is not None and reference_report is not None:
        baseline_matches_reference = reference_report["dataset_sha256"] == before[
            "dataset_sha256"
        ] and all(
            key in reference
            and old["selected"] == reference[key]["selected"]
            and old["evicted"] == reference[key]["evicted"]
            for key, old in original.items()
        )
    report = {
        "comparison_runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "dataset_sha256": before["dataset_sha256"],
        "repeats": repeats,
        "case_count": before["case_count"],
        "strategy_count": len(strategies),
        "baseline_matches_reference": baseline_matches_reference,
        "reference_directory": str(reference_directory)
        if reference_directory is not None
        else None,
        "before_repeat_stable": before["repeat_selection_stable"],
        "after_repeat_stable": after["repeat_selection_stable"],
        "changed_queries": len(changes),
        "unexpected_changes": [
            row
            for row in changes
            if row["category"] != "expired_candidates" or row["eviction_changed"]
        ],
        "regressions": [
            key for key, old in original.items() if old["pass"] and not updated[key]["pass"]
        ],
        "changes": changes,
        "comparisons": comparisons,
        "notes": [
            "No-refill caps the initial ranked prefix at 20 to reproduce the original boundary.",
            "Refill grows prefixes until 20 usable records, exhaustion, or default 100000 hit cap.",
            "Matched data, clocks, scoring, thresholds, budgets and capacities.",
            "Repeated runs are not independent cases; timing is descriptive, not a speedup claim.",
        ],
    }
    (output / "refill_comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (output / "refill_comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparisons[0]))
        writer.writeheader()
        writer.writerows(comparisons)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("experiments/datasets/challenge.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    report = run_refill_comparison(
        args.dataset, args.output, repeats=args.repeats, reference_directory=args.reference
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "changed_queries": report["changed_queries"],
                "regressions": len(report["regressions"]),
                "baseline_matches_reference": report["baseline_matches_reference"],
            }
        )
    )


if __name__ == "__main__":
    main()
