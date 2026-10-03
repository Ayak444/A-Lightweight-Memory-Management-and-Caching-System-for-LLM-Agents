from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from memlite.models import MemoryItem, MemoryStatus, MemoryType, SourceType, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    importance REAL NOT NULL CHECK (importance BETWEEN 0 AND 1),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    expires_at TEXT,
    metadata TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0 CHECK (access_count >= 0),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_scope_status
ON memories (scope_id, status, memory_type);

CREATE INDEX IF NOT EXISTS idx_memories_content_hash
ON memories (scope_id, memory_type, content_hash, status);

CREATE TABLE IF NOT EXISTS memory_relations (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, relation_type),
    FOREIGN KEY (source_id) REFERENCES memories(id),
    FOREIGN KEY (target_id) REFERENCES memories(id)
);
"""


class SQLiteMemoryStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self.initialize()

    def initialize(self) -> None:
        with self._connection:
            self._connection.executescript(SCHEMA)

    def save(self, item: MemoryItem, *, deduplicate: bool = True) -> MemoryItem:
        if deduplicate:
            duplicate = self._find_duplicate(item)
            if duplicate is not None:
                return duplicate

        with self._connection:
            self._insert(item)
        return item

    def get(self, memory_id: str) -> MemoryItem | None:
        row = self._connection.execute(
            "SELECT * FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        return self._from_row(row) if row is not None else None

    def list_active(
        self,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
        limit: int = 20,
    ) -> list[MemoryItem]:
        if memory_types is not None and not memory_types:
            return []
        parameters: list[Any] = [scope_id, MemoryStatus.ACTIVE.value, utc_now().isoformat()]
        type_clause = ""
        if memory_types:
            placeholders = ", ".join("?" for _ in memory_types)
            type_clause = f" AND memory_type IN ({placeholders})"
            parameters.extend(sorted(memory_type.value for memory_type in memory_types))
        parameters.append(limit)

        rows = self._connection.execute(
            f"""
            SELECT * FROM memories
            WHERE scope_id = ?
              AND status = ?
              AND (expires_at IS NULL OR expires_at > ?)
              {type_clause}
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def touch(self, memory_id: str, accessed_at: datetime) -> None:
        with self._connection:
            self._connection.execute(
                """
                UPDATE memories
                SET last_accessed_at = ?, access_count = access_count + 1
                WHERE id = ? AND status = ?
                """,
                (accessed_at.isoformat(), memory_id, MemoryStatus.ACTIVE.value),
            )

    def replace(self, previous_id: str, replacement: MemoryItem) -> MemoryItem:
        now = utc_now().isoformat()
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE memories
                SET status = ?, updated_at = ?, version = version + 1
                WHERE id = ? AND status = ?
                """,
                (
                    MemoryStatus.SUPERSEDED.value,
                    now,
                    previous_id,
                    MemoryStatus.ACTIVE.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"active memory not found: {previous_id}")

            self._insert(replacement)
            self._connection.execute(
                """
                INSERT INTO memory_relations (source_id, target_id, relation_type, created_at)
                VALUES (?, ?, 'supersedes', ?)
                """,
                (replacement.id, previous_id, now),
            )
        return replacement

    def soft_delete(self, memory_id: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE memories
                SET status = ?, updated_at = ?, version = version + 1
                WHERE id = ? AND status = ?
                """,
                (
                    MemoryStatus.DELETED.value,
                    utc_now().isoformat(),
                    memory_id,
                    MemoryStatus.ACTIVE.value,
                ),
            )
        return cursor.rowcount == 1

    def list_expired(
        self,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
        limit: int = 10_000,
    ) -> list[MemoryItem]:
        """Return active entries whose ``expires_at`` is in the past."""
        if memory_types is not None and not memory_types:
            return []
        parameters: list[Any] = [scope_id, MemoryStatus.ACTIVE.value, utc_now().isoformat()]
        type_clause = ""
        if memory_types:
            placeholders = ", ".join("?" for _ in memory_types)
            type_clause = f" AND memory_type IN ({placeholders})"
            parameters.extend(sorted(mt.value for mt in memory_types))
        parameters.append(limit)

        rows = self._connection.execute(
            f"""
            SELECT * FROM memories
            WHERE scope_id = ?
              AND status = ?
              AND expires_at IS NOT NULL
              AND expires_at <= ?
              {type_clause}
            ORDER BY expires_at ASC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def close(self) -> None:
        self._connection.close()

    def _find_duplicate(self, item: MemoryItem) -> MemoryItem | None:
        rows = self._connection.execute(
            """
            SELECT * FROM memories
            WHERE scope_id = ?
              AND memory_type = ?
              AND content_hash = ?
              AND status = ?
            ORDER BY created_at DESC
            """,
            (
                item.scope_id,
                item.memory_type.value,
                item.content_hash,
                MemoryStatus.ACTIVE.value,
            ),
        ).fetchall()
        for row in rows:
            duplicate = self._from_row(row)
            if not duplicate.is_expired():
                return duplicate
        return None

    def _insert(self, item: MemoryItem) -> None:
        self._connection.execute(
            """
            INSERT INTO memories (
                id, memory_type, scope_id, content, content_hash, source_type,
                source_ref, importance, confidence, expires_at, metadata,
                created_at, updated_at, last_accessed_at, access_count, version, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                item.memory_type.value,
                item.scope_id,
                item.content,
                item.content_hash,
                item.source_type.value,
                item.source_ref,
                item.importance,
                item.confidence,
                self._to_iso(item.expires_at),
                json.dumps(item.metadata, ensure_ascii=False, sort_keys=True),
                item.created_at.isoformat(),
                item.updated_at.isoformat(),
                self._to_iso(item.last_accessed_at),
                item.access_count,
                item.version,
                item.status.value,
            ),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            memory_type=MemoryType(row["memory_type"]),
            scope_id=row["scope_id"],
            content=row["content"],
            content_hash=row["content_hash"],
            source_type=SourceType(row["source_type"]),
            source_ref=row["source_ref"],
            importance=row["importance"],
            confidence=row["confidence"],
            expires_at=SQLiteMemoryStore._from_iso(row["expires_at"]),
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_accessed_at=SQLiteMemoryStore._from_iso(row["last_accessed_at"]),
            access_count=row["access_count"],
            version=row["version"],
            status=MemoryStatus(row["status"]),
        )

    @staticmethod
    def _to_iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _from_iso(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None


def count_rows(connection: sqlite3.Connection, table: str) -> int:
    allowed_tables: Iterable[str] = ("memories", "memory_relations")
    if table not in allowed_tables:
        raise ValueError(f"unsupported table: {table}")
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0])
