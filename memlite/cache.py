"""Semantic cache with exact and similarity-based lookup.

Cache scope uses a fingerprint derived from
(system_prompt_version, model_id, tool_schema_version, context_fingerprint)
so that identical queries under different configurations are isolated.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from memlite.embeddings.base import EmbeddingProvider
from memlite.models import MemoryType, normalize_content, utc_now
from memlite.vector.base import VectorIndex


def _scope_fingerprint(
    *,
    system_prompt_version: str = "",
    model_id: str = "",
    tool_schema_version: str = "",
    context_fingerprint: str = "",
) -> str:
    """Deterministic hash of the execution context that must match for a cache hit."""
    payload = json.dumps(
        {
            "system_prompt_version": system_prompt_version,
            "model_id": model_id,
            "tool_schema_version": tool_schema_version,
            "context_fingerprint": context_fingerprint,
        },
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _query_hash(query: str) -> str:
    return sha256(normalize_content(query).encode("utf-8")).hexdigest()


class CacheStatus(StrEnum):
    ACTIVE = "active"
    INVALIDATED = "invalidated"


class CacheEventType(StrEnum):
    HIT = "hit"
    MISS = "miss"
    REJECTED_HIT = "rejected_hit"
    STORE = "store"
    INVALIDATE = "invalidate"


@dataclass(frozen=True, slots=True)
class ScopeContext:
    """Captures the execution context that determines cache validity."""

    system_prompt_version: str = ""
    model_id: str = ""
    tool_schema_version: str = ""
    context_fingerprint: str = ""

    @property
    def fingerprint(self) -> str:
        return _scope_fingerprint(
            system_prompt_version=self.system_prompt_version,
            model_id=self.model_id,
            tool_schema_version=self.tool_schema_version,
            context_fingerprint=self.context_fingerprint,
        )


@dataclass(slots=True)
class CacheEntry:
    query: str
    response: str
    scope_id: str
    scope_fingerprint: str
    model_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    query_hash: str = ""
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
    last_accessed_at: datetime | None = None
    access_count: int = 0
    status: CacheStatus = CacheStatus.ACTIVE
    similarity: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if not self.response.strip():
            raise ValueError("response must not be empty")
        if not self.scope_id.strip():
            raise ValueError("scope_id must not be empty")
        if not self.query_hash:
            self.query_hash = _query_hash(self.query)

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and self.expires_at <= (now or utc_now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "query_hash": self.query_hash,
            "response": self.response,
            "scope_id": self.scope_id,
            "scope_fingerprint": self.scope_fingerprint,
            "model_id": self.model_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_accessed_at": (
                self.last_accessed_at.isoformat() if self.last_accessed_at else None
            ),
            "access_count": self.access_count,
            "status": self.status.value,
            "similarity": self.similarity,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class CacheLookupResult:
    """Outcome of a cache lookup, always contains the event log."""

    event_type: CacheEventType
    entry: CacheEntry | None
    similarity: float
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "entry_id": self.entry.id if self.entry else None,
            "similarity": self.similarity,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True, slots=True)
class CacheStats:
    total_entries: int
    active_entries: int
    total_lookups: int
    hits: int
    misses: int
    rejected_hits: int

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total_lookups if self.total_lookups > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "active_entries": self.active_entries,
            "total_lookups": self.total_lookups,
            "hits": self.hits,
            "misses": self.misses,
            "rejected_hits": self.rejected_hits,
            "hit_rate": self.hit_rate,
        }


CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_entries (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    response TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    scope_fingerprint TEXT NOT NULL,
    model_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0 CHECK (access_count >= 0),
    status TEXT NOT NULL,
    metadata TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_exact
ON cache_entries (scope_id, scope_fingerprint, query_hash, status);

CREATE INDEX IF NOT EXISTS idx_cache_scope_status
ON cache_entries (scope_id, status);

CREATE TABLE IF NOT EXISTS cache_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    cache_entry_id TEXT,
    scope_id TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    similarity REAL NOT NULL DEFAULT 0.0,
    rejection_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_events_type
ON cache_events (event_type);
"""


class SemanticCache:
    """Exact + semantic similarity cache with scope-aware invalidation."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        embedding_provider: EmbeddingProvider,
        vector_index: VectorIndex,
        similarity_threshold: float = 0.85,
        default_ttl_seconds: int | None = None,
    ) -> None:
        if not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0 and 1")
        if default_ttl_seconds is not None and default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be positive")

        self._db_path = Path(database_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._conn:
            self._conn.executescript(CACHE_SCHEMA)

        self._embedding = embedding_provider
        self._vector_index = vector_index
        self._threshold = similarity_threshold
        self._default_ttl = default_ttl_seconds

    @property
    def similarity_threshold(self) -> float:
        return self._threshold

    def lookup(
        self,
        query: str,
        *,
        scope_id: str,
        scope_context: ScopeContext,
    ) -> CacheLookupResult:
        """Try exact match first, then semantic similarity."""
        if not query.strip():
            raise ValueError("query must not be empty")
        if not scope_id.strip():
            raise ValueError("scope_id must not be empty")

        now = utc_now()
        qhash = _query_hash(query)
        fp = scope_context.fingerprint

        # 1. Exact match
        exact = self._find_exact(scope_id, fp, qhash, now)
        if exact is not None:
            self._touch(exact.id, now)
            result = CacheLookupResult(
                event_type=CacheEventType.HIT,
                entry=exact,
                similarity=1.0,
            )
            self._log_event(result, scope_id, qhash, now)
            return result

        # 2. Semantic similarity
        query_vector = self._embedding.embed([query])[0]
        from memlite.models import MemoryType  # avoid circular at module level

        hits = self._vector_index.search(
            query_vector,
            scope_id=f"cache:{scope_id}",
            model_id=self._embedding.model_id,
            limit=5,
        )

        for hit in hits:
            if hit.similarity < self._threshold:
                continue
            entry = self._get(hit.memory_id)
            if entry is None or entry.status is not CacheStatus.ACTIVE:
                continue
            if entry.is_expired(now):
                continue
            if entry.scope_fingerprint != fp:
                # Same query, different context — reject
                result = CacheLookupResult(
                    event_type=CacheEventType.REJECTED_HIT,
                    entry=entry,
                    similarity=hit.similarity,
                    rejection_reason="scope_fingerprint_mismatch",
                )
                self._log_event(result, scope_id, qhash, now)
                return result

            self._touch(entry.id, now)
            entry.similarity = hit.similarity
            result = CacheLookupResult(
                event_type=CacheEventType.HIT,
                entry=entry,
                similarity=hit.similarity,
            )
            self._log_event(result, scope_id, qhash, now)
            return result

        # 3. Cache miss
        result = CacheLookupResult(
            event_type=CacheEventType.MISS,
            entry=None,
            similarity=0.0,
        )
        self._log_event(result, scope_id, qhash, now)
        return result

    def store(
        self,
        query: str,
        response: str,
        *,
        scope_id: str,
        scope_context: ScopeContext,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CacheEntry:
        """Store a query-response pair in cache."""
        now = utc_now()
        effective_ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        entry = CacheEntry(
            query=query,
            response=response,
            scope_id=scope_id,
            scope_fingerprint=scope_context.fingerprint,
            model_id=scope_context.model_id,
            created_at=now,
            expires_at=now + timedelta(seconds=effective_ttl) if effective_ttl else None,
            metadata=dict(metadata or {}),
        )

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO cache_entries (
                    id, query, query_hash, response, scope_id, scope_fingerprint,
                    model_id, created_at, expires_at, last_accessed_at,
                    access_count, status, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.query,
                    entry.query_hash,
                    entry.response,
                    entry.scope_id,
                    entry.scope_fingerprint,
                    entry.model_id,
                    entry.created_at.isoformat(),
                    entry.expires_at.isoformat() if entry.expires_at else None,
                    None,
                    0,
                    CacheStatus.ACTIVE.value,
                    json.dumps(entry.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )

        # Index in vector store under cache-specific scope
        vector = self._embedding.embed([query])[0]
        self._vector_index.upsert(
            memory_id=entry.id,
            scope_id=f"cache:{scope_id}",
            memory_type=MemoryType.SEMANTIC,
            model_id=self._embedding.model_id,
            vector=vector,
        )

        self._log_event(
            CacheLookupResult(CacheEventType.STORE, entry, 1.0),
            scope_id,
            entry.query_hash,
            now,
        )
        return entry

    def invalidate(self, cache_id: str) -> bool:
        """Manually invalidate a single cache entry."""
        now = utc_now()
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE cache_entries SET status = ?, last_accessed_at = ?
                WHERE id = ? AND status = ?
                """,
                (CacheStatus.INVALIDATED.value, now.isoformat(), cache_id, CacheStatus.ACTIVE.value),
            )
        if cursor.rowcount == 1:
            self._vector_index.delete(cache_id)
            self._log_event(
                CacheLookupResult(CacheEventType.INVALIDATE, None, 0.0),
                "",
                "",
                now,
            )
            return True
        return False

    def invalidate_scope(self, scope_id: str) -> int:
        """Invalidate all active cache entries for a scope."""
        now = utc_now()
        rows = self._conn.execute(
            "SELECT id FROM cache_entries WHERE scope_id = ? AND status = ?",
            (scope_id, CacheStatus.ACTIVE.value),
        ).fetchall()
        count = 0
        for row in rows:
            if self.invalidate(row["id"]):
                count += 1
        return count

    def stats(self) -> CacheStats:
        """Return aggregate cache statistics."""
        total = self._count("SELECT COUNT(*) FROM cache_entries")
        active = self._count(
            "SELECT COUNT(*) FROM cache_entries WHERE status = ?",
            (CacheStatus.ACTIVE.value,),
        )
        hits = self._count(
            "SELECT COUNT(*) FROM cache_events WHERE event_type = ?",
            (CacheEventType.HIT.value,),
        )
        misses = self._count(
            "SELECT COUNT(*) FROM cache_events WHERE event_type = ?",
            (CacheEventType.MISS.value,),
        )
        rejected = self._count(
            "SELECT COUNT(*) FROM cache_events WHERE event_type = ?",
            (CacheEventType.REJECTED_HIT.value,),
        )
        return CacheStats(
            total_entries=total,
            active_entries=active,
            total_lookups=hits + misses + rejected,
            hits=hits,
            misses=misses,
            rejected_hits=rejected,
        )

    def list_active(self, scope_id: str, *, limit: int = 50) -> list[CacheEntry]:
        """List active cache entries for inspection."""
        rows = self._conn.execute(
            """
            SELECT * FROM cache_entries
            WHERE scope_id = ? AND status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (scope_id, CacheStatus.ACTIVE.value, limit),
        ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def close(self) -> None:
        self._conn.close()

    # -- internal helpers --

    def _find_exact(
        self, scope_id: str, fingerprint: str, query_hash: str, now: datetime
    ) -> CacheEntry | None:
        row = self._conn.execute(
            """
            SELECT * FROM cache_entries
            WHERE scope_id = ? AND scope_fingerprint = ? AND query_hash = ? AND status = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (scope_id, fingerprint, query_hash, CacheStatus.ACTIVE.value),
        ).fetchone()
        if row is None:
            return None
        entry = self._entry_from_row(row)
        if entry.is_expired(now):
            return None
        return entry

    def _get(self, cache_id: str) -> CacheEntry | None:
        row = self._conn.execute(
            "SELECT * FROM cache_entries WHERE id = ?", (cache_id,)
        ).fetchone()
        return self._entry_from_row(row) if row else None

    def _touch(self, cache_id: str, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                """
                UPDATE cache_entries
                SET last_accessed_at = ?, access_count = access_count + 1
                WHERE id = ?
                """,
                (now.isoformat(), cache_id),
            )

    def _log_event(
        self,
        result: CacheLookupResult,
        scope_id: str,
        query_hash: str,
        now: datetime,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO cache_events
                    (event_type, cache_entry_id, scope_id, query_hash,
                     similarity, rejection_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.event_type.value,
                    result.entry.id if result.entry else None,
                    scope_id,
                    query_hash,
                    result.similarity,
                    result.rejection_reason,
                    now.isoformat(),
                ),
            )

    def _count(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        row = self._conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _entry_from_row(row: sqlite3.Row) -> CacheEntry:
        return CacheEntry(
            id=row["id"],
            query=row["query"],
            query_hash=row["query_hash"],
            response=row["response"],
            scope_id=row["scope_id"],
            scope_fingerprint=row["scope_fingerprint"],
            model_id=row["model_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=(
                datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
            ),
            last_accessed_at=(
                datetime.fromisoformat(row["last_accessed_at"])
                if row["last_accessed_at"]
                else None
            ),
            access_count=row["access_count"],
            status=CacheStatus(row["status"]),
            metadata=json.loads(row["metadata"]),
        )
