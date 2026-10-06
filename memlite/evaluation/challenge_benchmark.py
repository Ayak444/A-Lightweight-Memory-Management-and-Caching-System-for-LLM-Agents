"""Predeclared synthetic retrieval/eviction experiments, without remote services."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import tempfile
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any
from unittest.mock import patch

from memlite.engine import MemLiteEngine
from memlite.evaluation.environment import save_environment
from memlite.models import MemoryItem, MemoryStatus, MemoryType
from memlite.policies.eviction import (
    EvictionPolicy,
    HybridEviction,
    ImportanceProtectedEviction,
    LFUEviction,
    LRUEviction,
    TTLEviction,
)
from memlite.policies.retrieval import RetrievalConfig, estimate_tokens

FIXED_NOW = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


@dataclass(frozen=True)
class ResearchStrategy:
    name: str
    max_results: int = 3
    eviction: str = "none"
    capacity: int | None = None
    history_window: int | None = None
    raw_history: bool = False
    protect_important: bool = False
    importance_threshold: float = 0.8
    confidence_threshold: float = 0.8
    protected_slots: int = 1

    def __post_init__(self) -> None:
        if self.eviction not in {"none", "ttl", "lru", "lfu", "hybrid_lru", "hybrid_lfu"}:
            raise ValueError("unknown eviction strategy")
        if not self.name.strip() or self.max_results < 1:
            raise ValueError("strategy name and positive max_results are required")
        if self.eviction not in {"none", "ttl"} and (self.capacity is None or self.capacity < 1):
            raise ValueError("capacity eviction requires positive capacity")
        if self.history_window is not None and self.history_window < 1:
            raise ValueError("history_window must be positive")
        if self.raw_history and self.eviction != "none":
            raise ValueError("raw history baselines cannot use memory eviction")
        if self.protect_important:
            if self.eviction in {"none", "ttl"} or self.capacity is None:
                raise ValueError("protection requires capacity eviction")
            ImportanceProtectedEviction(
                LRUEviction(self.capacity),
                importance_threshold=self.importance_threshold,
                confidence_threshold=self.confidence_threshold,
                protected_slots=self.protected_slots,
            )


STRATEGIES = (
    ResearchStrategy("B0_full_history", raw_history=True),
    ResearchStrategy("B1_recent10", history_window=10, raw_history=True),
    ResearchStrategy("hybrid_top1", max_results=1),
    ResearchStrategy("hybrid_top3"),
    ResearchStrategy("ttl_top3", eviction="ttl"),
    *(
        ResearchStrategy(f"{policy}_cap{capacity}_top3", eviction=policy, capacity=capacity)
        for capacity in (2, 4, 8)
        for policy in ("lru", "lfu", "hybrid_lru", "hybrid_lfu")
    ),
)


def make_challenge_dataset() -> dict[str, Any]:
    """Paired, disjoint project vocabularies; labels never become ranking signals."""
    cases: list[dict[str, Any]] = []
    for split, project in (("development", "atlas"), ("evaluation", "beacon")):

        def memory(
            key: str, text: str, *, _project: str = project, **kwargs: Any
        ) -> dict[str, Any]:
            return {"key": key, "content": f"{_project} {text}", **kwargs}

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
            cases.append(
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

        noise = [memory(f"noise-{i}", f"lunch meeting agenda item {i}") for i in range(15)]
        add(
            "long_history",
            "deployment region",
            [memory("region", "deployment region tokyo", age_days=90), *noise],
            ["region"],
        )
        add(
            "three_required",
            "deployment region database runtime",
            [
                memory("region", "deployment region tokyo", age_days=90),
                memory("database", "deployment database sqlite", age_days=60),
                *noise,
                memory("runtime", "deployment runtime python", age_days=1),
            ],
            ["region", "database", "runtime"],
        )
        add(
            "hot_pollution",
            "deployment database configuration",
            [
                memory(
                    "correct",
                    "deployment database configuration sqlite",
                    age_days=30,
                    access_age_days=30,
                    access_count=1,
                ),
                *[
                    memory(
                        f"wrong-{i}",
                        f"deployment database configuration mysql obsolete {i}",
                        age_days=1,
                        access_age_days=0,
                        access_count=50 + i,
                    )
                    for i in range(4)
                ],
            ],
            ["correct"],
            [f"wrong-{i}" for i in range(4)],
        )
        add(
            "fresh_correction",
            "deployment database configuration",
            [
                *[
                    memory(
                        f"wrong-{i}",
                        f"deployment database configuration mysql obsolete {i}",
                        age_days=30,
                        access_age_days=20,
                        access_count=50 + i,
                    )
                    for i in range(4)
                ],
                memory(
                    "correct",
                    "deployment database configuration sqlite",
                    age_days=1,
                    access_age_days=0,
                    access_count=1,
                ),
            ],
            ["correct"],
            [f"wrong-{i}" for i in range(4)],
        )
        add(
            "cold_important",
            "emergency recovery key",
            [
                memory(
                    "recovery",
                    "emergency recovery key vault",
                    age_days=90,
                    access_age_days=90,
                    access_count=0,
                    importance=1.0,
                ),
                *[
                    memory(
                        f"noise-{i}",
                        f"daily routine meeting {i}",
                        age_days=1,
                        access_age_days=0,
                        access_count=10 + i,
                    )
                    for i in range(10)
                ],
            ],
            ["recovery"],
        )
        add(
            "expired_candidates",
            "deployment database configuration mysql",
            [
                *[
                    memory(
                        f"expired-{i}",
                        f"deployment database configuration mysql {i}",
                        age_days=30,
                        expired=True,
                    )
                    for i in range(25)
                ],
                memory("correct", "deployment database configuration sqlite", age_days=1),
            ],
            ["correct"],
            [f"expired-{i}" for i in range(25)],
        )
    return {
        "version": "challenge-1.1.0",
        "provenance": "Authored synthetic stress cases, not real users or external held-out data.",
        "fixed_now": FIXED_NOW.isoformat(),
        "timestamp_rule": "Equal-age records use insertion order: later writes/accesses are newer.",
        "split_note": "Disjoint vocabulary pairs; same templates, not independent distributions.",
        "cases": cases,
    }


def validate_dataset(dataset: dict[str, Any]) -> None:
    if dataset.get("version") not in {"challenge-1.1.0", "protection-1.0.0"}:
        raise ValueError("unsupported challenge fixture version")
    if dataset.get("fixed_now") != FIXED_NOW.isoformat():
        raise ValueError("dataset clock differs from the declared experiment clock")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset requires nonempty cases")
    ids: set[str] = set()
    for case in cases:
        case_id = case["id"]
        if case_id in ids or case["split"] not in {"development", "evaluation"}:
            raise ValueError("duplicate case id or invalid split")
        ids.add(case_id)
        keys = [item["key"] for item in case["memories"]]
        expected, forbidden = set(case["expected"]), set(case["forbidden"])
        if len(keys) != len(set(keys)) or not expected:
            raise ValueError("memory keys must be unique and expected must be nonempty")
        if not (expected | forbidden) <= set(keys) or expected & forbidden:
            raise ValueError("invalid expected/forbidden labels")
        if not case["query"].strip():
            raise ValueError("query must be nonempty")


def evaluate_case(
    case: dict[str, Any],
    strategy: ResearchStrategy,
    database: Path,
    *,
    candidate_scan_limit: int | None = None,
) -> dict[str, Any]:
    config = RetrievalConfig(
        max_results=strategy.max_results, candidate_scan_limit=candidate_scan_limit
    )
    with ExitStack() as stack:
        # Freeze both eligibility and scoring; repeated runs must not depend on wall time.
        for module in ("memlite.models", "memlite.storage.sqlite", "memlite.policies.retrieval"):
            stack.enter_context(patch(f"{module}.utc_now", return_value=FIXED_NOW))
        engine = stack.enter_context(MemLiteEngine(database, retrieval_config=config))
        items: list[MemoryItem] = []
        for index, spec in enumerate(case["memories"]):
            offset = len(case["memories"]) - index
            created = FIXED_NOW - timedelta(days=spec.get("age_days", 1), seconds=offset)
            item = MemoryItem(
                id=sha256(f"{case['id']}:{spec['key']}".encode()).hexdigest(),
                memory_type=MemoryType.SEMANTIC,
                scope_id=case["id"],
                content=spec["content"],
                created_at=created,
                updated_at=created,
                last_accessed_at=FIXED_NOW
                - timedelta(
                    days=spec.get("access_age_days", spec.get("age_days", 1)), seconds=offset
                ),
                access_count=spec.get("access_count", 0),
                importance=spec.get("importance", 0.5),
                confidence=spec.get("confidence", 1.0),
                status=MemoryStatus(spec.get("status", "active")),
                expires_at=FIXED_NOW - timedelta(seconds=1) if spec.get("expired") else None,
            )
            # Test-only fixtures include expired rows and controlled access history.
            engine._store.save(item, deduplicate=False)
            engine._index(item)
            items.append(item)
        key_by_id = {
            item.id: spec["key"] for item, spec in zip(items, case["memories"], strict=True)
        }
        started = perf_counter()
        evicted: list[str] = []
        protected: list[str] = []
        if strategy.eviction != "none":
            policy: EvictionPolicy
            if strategy.eviction == "ttl":
                policy = TTLEviction()
            else:
                if strategy.capacity is None:
                    raise ValueError("capacity is required for capacity eviction")
                base_policy = (
                    LRUEviction(strategy.capacity)
                    if strategy.eviction in {"lru", "hybrid_lru"}
                    else LFUEviction(strategy.capacity)
                )
                capacity_policy = (
                    ImportanceProtectedEviction(
                        base_policy,
                        importance_threshold=strategy.importance_threshold,
                        confidence_threshold=strategy.confidence_threshold,
                        protected_slots=strategy.protected_slots,
                    )
                    if strategy.protect_important
                    else base_policy
                )
                policy = (
                    HybridEviction(capacity_policy)
                    if strategy.eviction.startswith("hybrid_")
                    else capacity_policy
                )
            result = engine.run_eviction(case["id"], policy=policy)
            evicted, protected = result.evicted_ids, result.protected_ids
        eviction_ms = (perf_counter() - started) * 1000
        retained = [
            key_by_id[item.id]
            for item in engine._store.list_active(scope_id=case["id"], limit=100_000)
        ]
        started = perf_counter()
        scan = {
            "search_rounds": 0,
            "scanned_hits": 0,
            "search_limit": 0,
            "scan_limit_reached": False,
        }
        if strategy.raw_history:
            selected_items = items[-strategy.history_window :] if strategy.history_window else items
            selected = [key_by_id[item.id] for item in selected_items]
            tokens = sum(estimate_tokens(item.content) for item in selected_items)
        else:
            response = engine.retrieve(case["query"], scope_id=case["id"])
            selected = [key_by_id[item_id] for item_id in response.selected_memory_ids]
            tokens = response.selected_tokens
            scan = {
                "search_rounds": response.search_rounds,
                "scanned_hits": response.scanned_hits,
                "search_limit": response.search_limit,
                "scan_limit_reached": response.scan_limit_reached,
            }
        retrieval_ms = (perf_counter() - started) * 1000
        remaining = len(engine._store.list_active(scope_id=case["id"], limit=100_000))
        expired_remaining = len(engine._store.list_expired(scope_id=case["id"], limit=100_000))
    relevant = set(selected) & set(case["expected"])
    pollution = set(selected) & set(case["forbidden"])
    protected_keys = [key_by_id[item_id] for item_id in protected]
    return {
        "case_id": case["id"],
        "split": case["split"],
        "category": case["category"],
        "strategy": strategy.name,
        "selected": selected,
        "evicted": [key_by_id[item_id] for item_id in evicted],
        "retained": retained,
        "protected": protected_keys,
        "expected_retention": len(set(retained) & set(case["expected"])) / len(case["expected"]),
        "protected_forbidden_count": len(set(protected_keys) & set(case["forbidden"])),
        "capacity_overflow": strategy.capacity is not None and remaining > strategy.capacity,
        "precision": len(relevant) / len(selected) if selected else 0.0,
        "recall": len(relevant) / len(case["expected"]),
        "pass": relevant == set(case["expected"]) and not pollution,
        "pollution_fraction": len(pollution) / len(selected) if selected else 0.0,
        "forbidden_hit": bool(pollution),
        "selected_tokens": tokens,
        "remaining_active": remaining,
        "remaining_expired": expired_remaining,
        "evicted_count": len(evicted),
        "eviction_ms": eviction_ms,
        "retrieval_ms": retrieval_ms,
    } | scan


def run_challenge_benchmark(
    dataset_path: str | Path,
    output_directory: str | Path,
    *,
    repeats: int = 3,
    strategies: tuple[ResearchStrategy, ...] = STRATEGIES,
    candidate_scan_limit: int | None = None,
) -> dict[str, Any]:
    if repeats < 3:
        raise ValueError("controlled experiments require at least three repetitions")
    if not strategies or len({strategy.name for strategy in strategies}) != len(strategies):
        raise ValueError("strategies must be nonempty and have unique names")
    path, output = Path(dataset_path), Path(output_directory)
    dataset = json.loads(path.read_text(encoding="utf-8"))
    validate_dataset(dataset)
    config = RetrievalConfig(max_results=3, candidate_scan_limit=candidate_scan_limit)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "challenge_report.json").exists():
        raise FileExistsError("choose a new output directory to preserve previous evidence")
    traces: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="memlite-challenge-") as temporary:
        for repetition in range(repeats):
            for strategy_index, strategy in enumerate(strategies):
                for case_index, case in enumerate(dataset["cases"]):
                    database = Path(temporary) / f"{repetition}-{strategy_index}-{case_index}.db"
                    traces.append(
                        evaluate_case(
                            case, strategy, database, candidate_scan_limit=candidate_scan_limit
                        )
                        | {"repeat": repetition + 1}
                    )
    aggregates: list[dict[str, Any]] = []
    metrics = (
        "precision",
        "recall",
        "pass",
        "pollution_fraction",
        "forbidden_hit",
        "selected_tokens",
        "remaining_active",
        "remaining_expired",
        "evicted_count",
        "eviction_ms",
        "retrieval_ms",
        "search_rounds",
        "scanned_hits",
        "scan_limit_reached",
        "expected_retention",
        "protected_forbidden_count",
        "capacity_overflow",
    )
    for split in sorted({case["split"] for case in dataset["cases"]}):
        for strategy in strategies:
            rows = [
                row for row in traces if row["split"] == split and row["strategy"] == strategy.name
            ]
            if rows:
                aggregates.append(
                    {"split": split, "strategy": strategy.name, "queries": len(rows)}
                    | {
                        f"mean_{metric}": statistics.mean(row[metric] for row in rows)
                        for metric in metrics
                    }
                )
    stable = all(
        len(
            {
                (tuple(row["selected"]), tuple(row["evicted"]), tuple(row["protected"]))
                for row in traces
                if row["case_id"] == case["id"] and row["strategy"] == strategy.name
            }
        )
        == 1
        for case in dataset["cases"]
        for strategy in strategies
    )
    report = {
        "dataset_version": dataset["version"],
        "dataset_sha256": sha256(path.read_bytes()).hexdigest(),
        "fixed_now": FIXED_NOW.isoformat(),
        "repeats": repeats,
        "case_count": len(dataset["cases"]),
        "repeat_selection_stable": stable,
        "retrieval_config": asdict(config),
        "strategies": [asdict(strategy) for strategy in strategies],
        "source_sha256": {
            str(source.relative_to(Path(__file__).resolve().parents[2])).replace("\\", "/"): sha256(
                source.read_bytes()
            ).hexdigest()
            for source in sorted(Path(__file__).resolve().parents[1].rglob("*.py"))
        },
        "results": aggregates,
        "notes": [
            "Synthetic stress cases; paired splits share templates, not independent held-out data.",
            "No parameter search or ranking changes based on evaluation labels.",
            "Each strategy overrides max_results; raw history bypasses retrieval_config.",
            "candidate_scan_limit=20 reproduces the original no-refill candidate boundary.",
            "Labels do not set confidence, importance or pollution_penalty.",
            "Three repetitions measure repeatability, not three independent samples.",
            "Precision/pollution are query-macro means; empty selection uses zero for both.",
            "Pass means all expected memories and no forbidden memories; not LLM task success.",
            "Raw-history baselines deliberately retain expired facts; retrieval filters expiry.",
            "No external API, billing, true semantic embeddings or answer quality measured.",
            "Database construction excluded; eviction and retrieval times reported separately.",
        ],
    }
    (output / "challenge_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "query_traces.json").write_text(
        json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "dataset_snapshot.json").write_bytes(path.read_bytes())
    with (output / "challenge_comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(aggregates[0]))
        writer.writeheader()
        writer.writerows(aggregates)
    save_environment(output / "environment.json", Path.cwd())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("experiments/datasets/challenge.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--candidate-scan-limit", type=int)
    parser.add_argument("--create-dataset", action="store_true")
    args = parser.parse_args()
    if args.create_dataset:
        if args.dataset.exists():
            raise FileExistsError("refusing to overwrite an existing dataset")
        args.dataset.parent.mkdir(parents=True, exist_ok=True)
        args.dataset.write_text(
            json.dumps(make_challenge_dataset(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    report = run_challenge_benchmark(
        args.dataset,
        args.output,
        repeats=args.repeats,
        candidate_scan_limit=args.candidate_scan_limit,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "cases": report["case_count"],
                "stable": report["repeat_selection_stable"],
            }
        )
    )


if __name__ == "__main__":
    main()
