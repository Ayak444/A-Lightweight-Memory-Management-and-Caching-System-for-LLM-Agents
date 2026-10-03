from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from memlite.evaluation.retrieval_benchmark import run_retrieval_benchmark


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run the deterministic retrieval baseline.")
    parser.add_argument(
        "dataset",
        nargs="?",
        default="experiments/datasets/mvp.json",
        help="Path to a benchmark dataset",
    )
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args(argv)

    result = run_retrieval_benchmark(Path(args.dataset))
    payload = result.summary()
    if args.summary_only:
        payload.pop("results", None)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
