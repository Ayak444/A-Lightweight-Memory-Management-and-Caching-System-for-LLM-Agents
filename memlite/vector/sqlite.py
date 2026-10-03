from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from memlite.models import MemoryType, utc_now
from memlite.vector.base import VectorSearchHit

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_vectors (
    memory_id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    model_id TEXT NOT NULL,
    dimension INTEGER NOT NULL CHECK (dimension > 0),
    vector TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vectors_scope_model_type
ON memory_vectors (scope_id, model_id, memory_type);
"""


class SQLiteVectorIndex:
    """Persistent exact-search vector baseline used before a real ANN backend."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        with self._connection:
            self._connection.executescript(SCHEMA)

    def upsert(
        self,
        *,
        memory_id: str,
        scope_id: str,
        memory_type: MemoryType,
        model_id: str,
        vector: list[float],
    ) -> None:
        self._validate_vector(vector)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO memory_vectors (
                    memory_id, scope_id, memory_type, model_id, dimension, vector, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    scope_id = excluded.scope_id,
                    memory_type = excluded.memory_type,
                    model_id = excluded.model_id,
                    dimension = excluded.dimension,
                    vector = excluded.vector,
                    updated_at = excluded.updated_at
                """,
                (
                    memory_id,
                    scope_id,
                    memory_type.value,
                    model_id,
                    len(vector),
                    json.dumps(vector, separators=(",", ":")),
                    utc_now().isoformat(),
                ),
            )

    def delete(self, memory_id: str) -> None:
        with self._connection:
            self._connection.execute(
                "DELETE FROM memory_vectors WHERE memory_id = ?",
                (memory_id,),
            )

    def clear_scope(self, scope_id: str) -> None:
        with self._connection:
            self._connection.execute(
                "DELETE FROM memory_vectors WHERE scope_id = ?",
                (scope_id,),
            )

    def search(
        self,
        vector: list[float],
        *,
        scope_id: str,
        model_id: str,
        memory_types: set[MemoryType] | None = None,
        limit: int = 20,
    ) -> list[VectorSearchHit]:
        self._validate_vector(vector)
        if limit < 1:
            raise ValueError("limit must be at least one")

        if memory_types is not None and not memory_types:
            return []
        parameters: list[Any] = [scope_id, model_id, len(vector)]
        type_clause = ""
        if memory_types:
            placeholders = ", ".join("?" for _ in memory_types)
            type_clause = f" AND memory_type IN ({placeholders})"
            parameters.extend(sorted(memory_type.value for memory_type in memory_types))

        rows = self._connection.execute(
            f"""
            SELECT memory_id, vector
            FROM memory_vectors
            WHERE scope_id = ? AND model_id = ? AND dimension = ? {type_clause}
            """,
            parameters,
        ).fetchall()

        hits = [
            VectorSearchHit(
                memory_id=row["memory_id"],
                similarity=self._dot(vector, json.loads(row["vector"])),
            )
            for row in rows
        ]
        return sorted(hits, key=lambda hit: (-hit.similarity, hit.memory_id))[:limit]

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _validate_vector(vector: list[float]) -> None:
        if not vector:
            raise ValueError("vector must not be empty")
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("vector values must be finite")

    @staticmethod
    def _dot(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError("vector dimensions do not match")
        return sum(
            left_value * right_value for left_value, right_value in zip(left, right, strict=False)
        )
