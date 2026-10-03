from __future__ import annotations

import json
import sys
from pathlib import Path

from memlite.evaluation.comparison_benchmark import run_comparisons


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    report = run_comparisons(
        Path("experiments/datasets/mvp.json"),
        Path("experiments/results/current"),
    )
    summary = {
        "dataset_version": report["dataset_version"],
        "dataset_sequences": report["dataset_sequences"],
        "strategy_comparison": report["strategy_comparison"],
        "token_budget_comparison": report["token_budget_comparison"],
        "corpus_latency_comparison": report["corpus_latency_comparison"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
