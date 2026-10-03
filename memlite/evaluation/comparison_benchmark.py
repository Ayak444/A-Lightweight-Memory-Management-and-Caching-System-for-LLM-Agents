from __future__ import annotations

import csv
import json
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from memlite.engine import MemLiteEngine
from memlite.evaluation.datasets import BenchmarkSequence, load_dataset
from memlite.models import MemoryType
from memlite.policies.retrieval import RetrievalConfig


@dataclass(frozen=True, slots=True)
class StrategySpec:
    name: str
    config: RetrievalConfig


STRATEGIES = (
    StrategySpec(
        name="similarity_only_top5",
        config=RetrievalConfig(
            max_results=5,
            similarity_weight=1.0,
            recency_weight=0.0,
            importance_weight=0.0,
            confidence_weight=0.0,
            frequency_weight=0.0,
        ),
    ),
    StrategySpec(name="hybrid_top5", config=RetrievalConfig(max_results=5)),
    StrategySpec(name="hybrid_top3", config=RetrievalConfig(max_results=3)),
    StrategySpec(name="hybrid_top1", config=RetrievalConfig(max_results=1)),
    StrategySpec(
        name="hybrid_top3_strict",
        config=RetrievalConfig(max_results=3, min_similarity=0.20),
    ),
)


def run_comparisons(
    dataset_path: str | Path,
    output_directory: str | Path,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="memlite-comparison-") as temporary_directory:
        work_directory = Path(temporary_directory)
        strategy_results = [
            _evaluate_strategy(dataset.sequences, strategy, work_directory)
            for strategy in STRATEGIES
        ]
        token_budget_results = [
            _evaluate_strategy(
                dataset.sequences,
                StrategySpec(
                    name=f"budget_{budget}",
                    config=RetrievalConfig(token_budget=budget, max_results=5),
                ),
                work_directory,
            )
            | {"token_budget": budget}
            for budget in (8, 16, 32, 64, 128, 500)
        ]
        latency_results = _benchmark_corpus_latency(work_directory)

    report = {
        "dataset_version": dataset.version,
        "dataset_sequences": len(dataset.sequences),
        "strategy_comparison": strategy_results,
        "token_budget_comparison": token_budget_results,
        "corpus_latency_comparison": latency_results,
        "notes": [
            "All figures use the deterministic lexical embedding baseline.",
            "Latency excludes remote embedding and LLM calls.",
            "Results describe the current offline prototype, not production performance.",
        ],
    }
    (output_directory / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(output_directory / "strategy_comparison.csv", strategy_results)
    _write_csv(output_directory / "token_budget_comparison.csv", token_budget_results)
    _write_csv(output_directory / "corpus_latency_comparison.csv", latency_results)
    return report


def _evaluate_strategy(
    sequences: list[BenchmarkSequence],
    strategy: StrategySpec,
    work_directory: Path,
) -> dict[str, Any]:
    precisions: list[float] = []
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    passes: list[bool] = []
    selected_tokens: list[int] = []
    latencies: list[float] = []

    for sequence in sequences:
        database_path = work_directory / f"{strategy.name}-{sequence.sequence_id}.db"
        with MemLiteEngine(database_path, retrieval_config=strategy.config) as engine:
            key_by_id = _populate(engine, sequence)
            for query in sequence.queries:
                started = perf_counter()
                response = engine.retrieve(
                    str(query["input"]),
                    scope_id=str(query.get("scope", sequence.sequence_id)),
                )
                latencies.append((perf_counter() - started) * 1_000)
                selected = [key_by_id[memory_id] for memory_id in response.selected_memory_ids]
                expected = {str(key) for key in query["expected_memory_keys"]}
                forbidden = {str(key) for key in query.get("forbidden_memory_keys", [])}
                selected_set = set(selected)
                relevant_count = len(selected_set & expected)
                precisions.append(relevant_count / len(selected) if selected else 0.0)
                recalls.append(relevant_count / len(expected))
                reciprocal_ranks.append(_reciprocal_rank(selected, expected))
                passes.append(
                    expected.issubset(selected_set) and selected_set.isdisjoint(forbidden)
                )
                selected_tokens.append(response.selected_tokens)

    return {
        "strategy": strategy.name,
        "queries": len(passes),
        "pass_rate": statistics.fmean(passes),
        "mean_precision": statistics.fmean(precisions),
        "mean_recall": statistics.fmean(recalls),
        "mean_reciprocal_rank": statistics.fmean(reciprocal_ranks),
        "mean_selected_tokens": statistics.fmean(selected_tokens),
        "latency_ms_p50": statistics.median(latencies),
        "latency_ms_p95": _percentile(latencies, 0.95),
    }


def _populate(engine: MemLiteEngine, sequence: BenchmarkSequence) -> dict[str, str]:
    key_by_id: dict[str, str] = {}
    id_by_key: dict[str, str] = {}
    for raw_memory in sequence.memories:
        key = str(raw_memory["key"])
        if raw_memory.get("supersedes"):
            item = engine.supersede(
                id_by_key[str(raw_memory["supersedes"])],
                content=str(raw_memory["content"]),
            )
        else:
            metadata: dict[str, object] = {}
            if "pollution_penalty" in raw_memory:
                metadata["pollution_penalty"] = float(raw_memory["pollution_penalty"])
            item = engine.remember(
                memory_type=MemoryType(str(raw_memory["type"])),
                scope_id=str(raw_memory.get("scope", sequence.sequence_id)),
                content=str(raw_memory["content"]),
                importance=float(raw_memory.get("importance", 0.5)),
                confidence=float(raw_memory.get("confidence", 1.0)),
                metadata=metadata,
            )
        id_by_key[key] = item.id
        key_by_id[item.id] = key
    return key_by_id


def _benchmark_corpus_latency(work_directory: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for corpus_size in (10, 100, 500, 1_000, 2_000):
        database_path = work_directory / f"latency-{corpus_size}.db"
        with MemLiteEngine(database_path) as engine:
            for index in range(corpus_size - 1):
                engine.remember(
                    memory_type=MemoryType.EPISODIC,
                    scope_id="latency-test",
                    content=" ".join(
                        (
                            "Unrelated benchmark event",
                            f"number {index}",
                            "about routine project activity",
                        )
                    ),
                )
            engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="latency-test",
                content="The project metadata source of truth is SQLite",
                importance=1.0,
            )

            engine.retrieve(
                "Which database is the metadata source of truth?", scope_id="latency-test"
            )
            samples: list[float] = []
            for _ in range(30):
                started = perf_counter()
                engine.retrieve(
                    "Which database is the metadata source of truth?",
                    scope_id="latency-test",
                )
                samples.append((perf_counter() - started) * 1_000)

        results.append(
            {
                "corpus_size": corpus_size,
                "runs": len(samples),
                "latency_ms_p50": statistics.median(samples),
                "latency_ms_p95": _percentile(samples, 0.95),
            }
        )
    return results


def _reciprocal_rank(selected: list[str], expected: set[str]) -> float:
    for rank, key in enumerate(selected, start=1):
        if key in expected:
            return 1.0 / rank
    return 0.0


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, math_ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def math_ceil(value: float) -> int:
    integer = int(value)
    return integer if integer == value else integer + 1


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
