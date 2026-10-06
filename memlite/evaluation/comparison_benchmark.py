from __future__ import annotations

import csv
import json
import statistics
import tempfile
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from memlite.engine import MemLiteEngine
from memlite.evaluation.datasets import BenchmarkSequence, load_dataset
from memlite.evaluation.environment import save_environment
from memlite.evaluation.run_log import Metric, RetrievalEvent, Run, RunLogStore
from memlite.evaluation.summary import save_summary
from memlite.models import MemoryType
from memlite.policies.retrieval import RetrievalConfig, estimate_tokens


@dataclass(frozen=True, slots=True)
class StrategySpec:
    name: str
    config: RetrievalConfig
    history_window: int | None = None


STRATEGIES = (
    StrategySpec(
        name="B0_full_history",
        config=RetrievalConfig(
            candidate_limit=99999,
            max_results=99999,
            token_budget=999999,
            min_similarity=0.0,
            similarity_weight=0.0,
            recency_weight=1.0,
            importance_weight=0.0,
            confidence_weight=0.0,
            frequency_weight=0.0,
        ),
    ),
    StrategySpec(
        name="B1_recent_window",
        history_window=10,
        config=RetrievalConfig(
            candidate_limit=99999,
            max_results=10,
            token_budget=1024,
            min_similarity=0.0,
            similarity_weight=0.0,
            recency_weight=1.0,
            importance_weight=0.0,
            confidence_weight=0.0,
            frequency_weight=0.0,
        ),
    ),
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
    experiment_id = str(uuid4())

    with (
        tempfile.TemporaryDirectory(prefix="memlite-comparison-") as temporary_directory,
        RunLogStore(output_directory / "runs.db") as run_log,
    ):
        work_directory = Path(temporary_directory)
        strategy_results = [
            _evaluate_strategy(dataset.sequences, strategy, work_directory, run_log, experiment_id)
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
                run_log,
                experiment_id,
            )
            | {"token_budget": budget}
            for budget in (8, 16, 32, 64, 128, 500)
        ]
        latency_results = _benchmark_corpus_latency(work_directory)

    report = {
        "dataset_version": dataset.version,
        "dataset_sha256": sha256(Path(dataset_path).read_bytes()).hexdigest(),
        "experiment_id": experiment_id,
        "dataset_sequences": len(dataset.sequences),
        "strategy_comparison": strategy_results,
        "token_budget_comparison": token_budget_results,
        "corpus_latency_comparison": latency_results,
        "notes": [
            "B0 uses raw memory-write history; B1 uses the last 10 writes per scope.",
            "History baselines include replaced facts; they bypass vector scoring and dedup.",
            "Pass rate measures retrieval constraints, not LLM answer quality.",
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
    save_environment(output_directory / "environment.json", Path.cwd())
    save_summary(output_directory)
    return report


def _evaluate_strategy(
    sequences: list[BenchmarkSequence],
    strategy: StrategySpec,
    work_directory: Path,
    run_log: RunLogStore | None = None,
    experiment_id: str = "",
) -> dict[str, Any]:
    precisions: list[float] = []
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    passes: list[bool] = []
    selected_tokens: list[int] = []
    latencies: list[float] = []
    run_id = str(uuid4())
    if run_log is not None:
        run_log.create_run(
            Run(
                id=run_id,
                experiment_id=experiment_id,
                strategy=strategy.name,
                config=asdict(strategy.config) | {"history_window": strategy.history_window},
                model="deterministic-hash",
                status="running",
            )
        )

    for sequence in sequences:
        database_path = work_directory / f"{strategy.name}-{sequence.sequence_id}.db"
        with MemLiteEngine(database_path, retrieval_config=strategy.config) as engine:
            key_by_id = _populate(engine, sequence)
            for query in sequence.queries:
                started = perf_counter()
                query_text = str(query["input"])
                scope_id = str(query.get("scope", sequence.sequence_id))
                if strategy.name in {"B0_full_history", "B1_recent_window"}:
                    selected, token_count = _select_history(sequence, strategy, scope_id)
                    latencies.append((perf_counter() - started) * 1_000)
                else:
                    response = engine.retrieve(query_text, scope_id=scope_id)
                    selected = [key_by_id[mid] for mid in response.selected_memory_ids]
                    token_count = response.selected_tokens
                    latencies.append((perf_counter() - started) * 1_000)
                    if run_log is not None:
                        for candidate in response.candidates:
                            run_log.log_retrieval_event(
                                RetrievalEvent(
                                    run_id=run_id,
                                    query=query_text,
                                    memory_id=candidate.memory.id,
                                    estimated_tokens=candidate.estimated_tokens,
                                    selected=candidate.selected,
                                    rejection_reason=candidate.rejection_reason,
                                    similarity=candidate.score.similarity,
                                    recency=candidate.score.recency,
                                    importance=candidate.score.importance,
                                    confidence=candidate.score.confidence,
                                    frequency=candidate.score.frequency,
                                    pollution_penalty=candidate.score.pollution_penalty,
                                    final_score=candidate.score.final_score,
                                )
                            )
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
                selected_tokens.append(token_count)

    result = {
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
    if run_log is not None:
        for name, value in result.items():
            if isinstance(value, (float, int)):
                run_log.log_metric(Metric(run_id=run_id, metric_name=name, value=float(value)))
        run_log.finish_run(run_id)
    return result


def _select_history(
    sequence: BenchmarkSequence,
    strategy: StrategySpec,
    scope_id: str,
) -> tuple[list[str], int]:
    scopes: dict[str, str] = {}
    history: list[tuple[str, str]] = []
    for raw in sequence.memories:
        key = str(raw["key"])
        previous = raw.get("supersedes")
        memory_scope = (
            scopes[str(previous)] if previous else str(raw.get("scope", sequence.sequence_id))
        )
        scopes[key] = memory_scope
        if memory_scope == scope_id:
            history.append((key, str(raw["content"])))
    if strategy.history_window is not None:
        history = history[-strategy.history_window :]
    # Recent-first fits the window budget; restore chronological prompt order.
    selected: list[tuple[str, str]] = []
    for item in reversed(history):
        if estimate_tokens("\n".join(content for _, content in [item, *selected])) <= (
            strategy.config.token_budget
        ):
            selected.insert(0, item)
    text = "\n".join(content for _, content in selected)
    return [key for key, _ in selected], estimate_tokens(text) if selected else 0


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
