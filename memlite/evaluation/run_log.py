"""Persistent run / event log and metrics store.

PROJECT_GUIDE requires three tables:
- ``runs``: experiment id, policy config, model, input, output, status, timestamps
- ``retrieval_events``: candidate, scores, selected, token count
- ``metrics``: run id, metric name, value, unit, metadata

All tables live in the same SQLite database as the memory store for simplicity.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from memlite.models import utc_now

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

RUN_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    strategy TEXT NOT NULL,
    config TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_runs_experiment ON runs (experiment_id);

CREATE TABLE IF NOT EXISTS retrieval_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    query TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    similarity REAL NOT NULL,
    recency REAL NOT NULL,
    importance REAL NOT NULL,
    confidence REAL NOT NULL,
    frequency REAL NOT NULL,
    pollution_penalty REAL NOT NULL DEFAULT 0,
    final_score REAL NOT NULL,
    estimated_tokens INTEGER NOT NULL,
    selected INTEGER NOT NULL DEFAULT 0,
    rejection_reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_retrieval_events_run ON retrieval_events (run_id);

CREATE TABLE IF NOT EXISTS metrics (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_metrics_run ON metrics (run_id);
"""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Run:
    id: str
    experiment_id: str
    strategy: str
    config: dict[str, Any]
    model: str = ""
    status: str = "pending"
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalEvent:
    run_id: str
    query: str
    memory_id: str
    similarity: float
    recency: float
    importance: float
    confidence: float
    frequency: float
    pollution_penalty: float
    final_score: float
    estimated_tokens: int
    selected: bool
    rejection_reason: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True, slots=True)
class Metric:
    run_id: str
    metric_name: str
    value: float
    unit: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class RunLogStore:
    """Persistent store for experiment runs, retrieval events, and metrics."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        with self._connection:
            self._connection.executescript(RUN_LOG_SCHEMA)

    # -- Runs --

    def create_run(self, run: Run) -> Run:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO runs (
                    id, experiment_id, strategy, config, model, status,
                    started_at, finished_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.experiment_id,
                    run.strategy,
                    json.dumps(run.config, ensure_ascii=False),
                    run.model,
                    run.status,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat() if run.finished_at else None,
                    json.dumps(run.metadata, ensure_ascii=False),
                ),
            )
        return run

    def finish_run(self, run_id: str, *, status: str = "completed") -> None:
        now = utc_now()
        with self._connection:
            self._connection.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
                (status, now.isoformat(), run_id),
            )

    def get_run(self, run_id: str) -> Run | None:
        row = self._connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return Run(
            id=row["id"],
            experiment_id=row["experiment_id"],
            strategy=row["strategy"],
            config=json.loads(row["config"]),
            model=row["model"],
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            metadata=json.loads(row["metadata"]),
        )

    def list_runs(self, experiment_id: str | None = None, *, limit: int = 100) -> list[Run]:
        if experiment_id:
            rows = self._connection.execute(
                "SELECT * FROM runs WHERE experiment_id = ? ORDER BY started_at DESC LIMIT ?",
                (experiment_id, limit),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            Run(
                id=r["id"],
                experiment_id=r["experiment_id"],
                strategy=r["strategy"],
                config=json.loads(r["config"]),
                model=r["model"],
                status=r["status"],
                started_at=datetime.fromisoformat(r["started_at"]),
                finished_at=datetime.fromisoformat(r["finished_at"]) if r["finished_at"] else None,
                metadata=json.loads(r["metadata"]),
            )
            for r in rows
        ]

    # -- Retrieval Events --

    def log_retrieval_event(self, event: RetrievalEvent) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO retrieval_events
                    (id, run_id, query, memory_id, similarity, recency, importance,
                     confidence, frequency, pollution_penalty, final_score,
                     estimated_tokens, selected, rejection_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.run_id,
                    event.query,
                    event.memory_id,
                    event.similarity,
                    event.recency,
                    event.importance,
                    event.confidence,
                    event.frequency,
                    event.pollution_penalty,
                    event.final_score,
                    event.estimated_tokens,
                    1 if event.selected else 0,
                    event.rejection_reason,
                    utc_now().isoformat(),
                ),
            )

    def log_retrieval_events(self, events: list[RetrievalEvent]) -> None:
        for event in events:
            self.log_retrieval_event(event)

    def list_retrieval_events(self, run_id: str) -> list[RetrievalEvent]:
        rows = self._connection.execute(
            "SELECT * FROM retrieval_events WHERE run_id = ? ORDER BY final_score DESC",
            (run_id,),
        ).fetchall()
        return [
            RetrievalEvent(
                id=r["id"],
                run_id=r["run_id"],
                query=r["query"],
                memory_id=r["memory_id"],
                similarity=r["similarity"],
                recency=r["recency"],
                importance=r["importance"],
                confidence=r["confidence"],
                frequency=r["frequency"],
                pollution_penalty=r["pollution_penalty"],
                final_score=r["final_score"],
                estimated_tokens=r["estimated_tokens"],
                selected=bool(r["selected"]),
                rejection_reason=r["rejection_reason"],
            )
            for r in rows
        ]

    # -- Metrics --

    def log_metric(self, metric: Metric) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO metrics (id, run_id, metric_name, value, unit, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metric.id,
                    metric.run_id,
                    metric.metric_name,
                    metric.value,
                    metric.unit,
                    json.dumps(metric.metadata, ensure_ascii=False),
                    utc_now().isoformat(),
                ),
            )

    def log_metrics(self, metrics: list[Metric]) -> None:
        for metric in metrics:
            self.log_metric(metric)

    def list_metrics(self, run_id: str) -> list[Metric]:
        rows = self._connection.execute(
            "SELECT * FROM metrics WHERE run_id = ? ORDER BY metric_name", (run_id,)
        ).fetchall()
        return [
            Metric(
                id=r["id"],
                run_id=r["run_id"],
                metric_name=r["metric_name"],
                value=r["value"],
                unit=r["unit"],
                metadata=json.loads(r["metadata"]),
            )
            for r in rows
        ]

    # -- Lifecycle --

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> RunLogStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
