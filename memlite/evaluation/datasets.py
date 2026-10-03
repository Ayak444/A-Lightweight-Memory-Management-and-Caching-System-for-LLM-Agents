from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_CATEGORIES = {
    "conflict",
    "irrelevant",
    "long_horizon",
    "preference",
    "repetition",
    "scope_isolation",
    "update",
}


@dataclass(frozen=True, slots=True)
class BenchmarkSequence:
    sequence_id: str
    category: str
    description: str
    memories: list[dict[str, Any]]
    queries: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class BenchmarkDataset:
    version: str
    sequences: list[BenchmarkSequence]

    @property
    def categories(self) -> set[str]:
        return {sequence.category for sequence in self.sequences}


def load_dataset(path: str | Path) -> BenchmarkDataset:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    version = _required_text(payload, "version")
    raw_sequences = payload.get("sequences")
    if not isinstance(raw_sequences, list) or not raw_sequences:
        raise ValueError("dataset sequences must be a non-empty list")

    sequences: list[BenchmarkSequence] = []
    seen_ids: set[str] = set()
    for raw_sequence in raw_sequences:
        if not isinstance(raw_sequence, dict):
            raise ValueError("each sequence must be an object")
        sequence_id = _required_text(raw_sequence, "sequence_id")
        if sequence_id in seen_ids:
            raise ValueError(f"duplicate sequence_id: {sequence_id}")
        seen_ids.add(sequence_id)

        category = _required_text(raw_sequence, "category")
        memories = raw_sequence.get("memories")
        queries = raw_sequence.get("queries")
        if not isinstance(memories, list) or not memories:
            raise ValueError(f"{sequence_id}: memories must be a non-empty list")
        if not isinstance(queries, list) or not queries:
            raise ValueError(f"{sequence_id}: queries must be a non-empty list")
        for query in queries:
            if not isinstance(query, dict) or not query.get("expected_memory_keys"):
                raise ValueError(f"{sequence_id}: each query needs expected_memory_keys")

        sequences.append(
            BenchmarkSequence(
                sequence_id=sequence_id,
                category=category,
                description=_required_text(raw_sequence, "description"),
                memories=memories,
                queries=queries,
            )
        )

    dataset = BenchmarkDataset(version=version, sequences=sequences)
    missing_categories = REQUIRED_CATEGORIES - dataset.categories
    if missing_categories:
        missing = ", ".join(sorted(missing_categories))
        raise ValueError(f"dataset is missing required categories: {missing}")
    return dataset


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
