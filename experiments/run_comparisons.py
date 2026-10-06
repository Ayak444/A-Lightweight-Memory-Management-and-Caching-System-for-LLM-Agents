from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from memlite.evaluation.agent_benchmark import run_agent_cache_benchmark
from memlite.evaluation.comparison_benchmark import run_comparisons
from memlite.evaluation.summary import save_summary


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Run offline retrieval and agent-cache comparisons"
    )
    parser.add_argument("--dataset", type=Path, default=Path("experiments/datasets/mvp.json"))
    parser.add_argument("--output", type=Path, default=Path("experiments/results/current"))
    args = parser.parse_args()
    report = run_comparisons(args.dataset, args.output)
    agent_report = run_agent_cache_benchmark(args.output)
    save_summary(args.output)
    summary = {
        "dataset_version": report["dataset_version"],
        "dataset_sequences": report["dataset_sequences"],
        "strategy_comparison": report["strategy_comparison"],
        "token_budget_comparison": report["token_budget_comparison"],
        "corpus_latency_comparison": report["corpus_latency_comparison"],
        "agent_cache_comparison": agent_report,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
