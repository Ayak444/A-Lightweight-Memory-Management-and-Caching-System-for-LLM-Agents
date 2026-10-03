from __future__ import annotations

import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from memlite.engine import MemLiteEngine
from memlite.evaluation.datasets import BenchmarkDataset, BenchmarkSequence, load_dataset
from memlite.models import MemoryType


@dataclass(frozen=True, slots=True)
class QueryResult:
    sequence_id: str
    query_id: str
    category: str
    precision: float
    recall: float
    reciprocal_rank: float
    passed: bool
    latency_ms: float
    selected_keys: list[str]
    expected_keys: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence_id": self.sequence_id,
            "query_id": self.query_id,
            "category": self.category,
            "precision": self.precision,
            "recall": self.recall,
            "reciprocal_rank": self.reciprocal_rank,
            "passed": self.passed,
            "latency_ms": self.latency_ms,
            "selected_keys": self.selected_keys,
            "expected_keys": self.expected_keys,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    dataset_version: str
    query_results: list[QueryResult]

    def summary(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "queries": len(self.query_results),
            "pass_rate": statistics.fmean(result.passed for result in self.query_results),
            "mean_precision": statistics.fmean(result.precision for result in self.query_results),
            "mean_recall": statistics.fmean(result.recall for result in self.query_results),
            "mean_reciprocal_rank": statistics.fmean(
                result.reciprocal_rank for result in self.query_results
            ),
            "latency_ms_p50": statistics.median(result.latency_ms for result in self.query_results),
            "results": [result.to_dict() for result in self.query_results],
        }


def run_retrieval_benchmark(path: str | Path) -> BenchmarkResult:
    dataset = load_dataset(path)
    results: list[QueryResult] = []
    with tempfile.TemporaryDirectory(prefix="memlite-benchmark-") as temporary_directory:
        base_path = Path(temporary_directory)
        for sequence in dataset.sequences:
            results.extend(_run_sequence(dataset, sequence, base_path))
    return BenchmarkResult(dataset_version=dataset.version, query_results=results)


def _run_sequence(
    dataset: BenchmarkDataset,
    sequence: BenchmarkSequence,
    base_path: Path,
) -> list[QueryResult]:
    del dataset
    database_path = base_path / f"{sequence.sequence_id}.db"
    key_by_id: dict[str, str] = {}
    id_by_key: dict[str, str] = {}
    default_scope = sequence.sequence_id

    with MemLiteEngine(database_path) as engine:
        for raw_memory in sequence.memories:
            memory_key = str(raw_memory["key"])
            superseded_key = raw_memory.get("supersedes")
            if superseded_key:
                replacement = engine.supersede(
                    id_by_key[str(superseded_key)],
                    content=str(raw_memory["content"]),
                )
                key_by_id[replacement.id] = memory_key
                id_by_key[memory_key] = replacement.id
                continue

            metadata: dict[str, object] = {}
            if "pollution_penalty" in raw_memory:
                metadata["pollution_penalty"] = float(raw_memory["pollution_penalty"])
            item = engine.remember(
                memory_type=MemoryType(str(raw_memory["type"])),
                scope_id=str(raw_memory.get("scope", default_scope)),
                content=str(raw_memory["content"]),
                importance=float(raw_memory.get("importance", 0.5)),
                confidence=float(raw_memory.get("confidence", 1.0)),
                metadata=metadata,
            )
            key_by_id[item.id] = memory_key
            id_by_key[memory_key] = item.id

        return [
            _evaluate_query(engine, sequence, query, key_by_id, default_scope)
            for query in sequence.queries
        ]


def _evaluate_query(
    engine: MemLiteEngine,
    sequence: BenchmarkSequence,
    query: dict[str, Any],
    key_by_id: dict[str, str],
    default_scope: str,
) -> QueryResult:
    started = perf_counter()
    response = engine.retrieve(
        str(query["input"]),
        scope_id=str(query.get("scope", default_scope)),
    )
    latency_ms = (perf_counter() - started) * 1_000

    selected_keys = [key_by_id[memory_id] for memory_id in response.selected_memory_ids]
    expected_keys = [str(key) for key in query["expected_memory_keys"]]
    forbidden_keys = {str(key) for key in query.get("forbidden_memory_keys", [])}
    expected_set = set(expected_keys)
    selected_set = set(selected_keys)
    relevant_count = len(selected_set & expected_set)
    precision = relevant_count / len(selected_keys) if selected_keys else 0.0
    recall = relevant_count / len(expected_keys)

    reciprocal_rank = 0.0
    for rank, key in enumerate(selected_keys, start=1):
        if key in expected_set:
            reciprocal_rank = 1.0 / rank
            break

    return QueryResult(
        sequence_id=sequence.sequence_id,
        query_id=str(query["id"]),
        category=sequence.category,
        precision=precision,
        recall=recall,
        reciprocal_rank=reciprocal_rank,
        passed=expected_set.issubset(selected_set) and selected_set.isdisjoint(forbidden_keys),
        latency_ms=latency_ms,
        selected_keys=selected_keys,
        expected_keys=expected_keys,
    )
