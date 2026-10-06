from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from memlite.cache import CacheEventType, ScopeContext
from memlite.engine import MemLiteEngine
from memlite.models import MemoryItem, MemoryStatus, MemoryType, SourceType
from memlite.policies.eviction import TTLEviction
from memlite.skill_cli import execute_request

NOW = datetime(2030, 1, 1, tzinfo=UTC)


class TTLCorrectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "memory.db"

    def test_correction_preserves_absolute_expiry_without_resetting_ttl(self) -> None:
        with MemLiteEngine(self.database) as engine:
            with patch("memlite.manager.utc_now", return_value=NOW):
                old = engine.remember(
                    memory_type=MemoryType.WORKING,
                    scope_id="project:a",
                    content="database mysql",
                    ttl_seconds=120,
                    metadata={"ticket": "42"},
                )
            with patch("memlite.manager.utc_now", return_value=NOW + timedelta(seconds=90)):
                replacement = engine.supersede(
                    old.id, content="database sqlite", source_ref="decision:42"
                )
            self.assertEqual(replacement.expires_at, NOW + timedelta(seconds=120))
            self.assertEqual(replacement.metadata, {"ticket": "42"})
            self.assertEqual(replacement.source_ref, "decision:42")
            self.assertIs(replacement.source_type, SourceType.USER)
            self.assertIs(engine._store.get(old.id).status, MemoryStatus.SUPERSEDED)
            relation = engine._store._connection.execute(
                "SELECT source_id, target_id FROM memory_relations WHERE relation_type = ?",
                ("supersedes",),
            ).fetchone()
            self.assertEqual(tuple(relation), (replacement.id, old.id))

    def test_expired_and_exact_boundary_correction_are_rejected_without_mutation(self) -> None:
        for expires in (NOW - timedelta(seconds=1), NOW):
            with self.subTest(expires=expires), MemLiteEngine(self.database) as engine:
                old = engine._store.save(
                    MemoryItem(
                        memory_type=MemoryType.WORKING,
                        scope_id="project:a",
                        content=f"expired {expires}",
                        expires_at=expires,
                    )
                )
                with (
                    patch("memlite.manager.utc_now", return_value=NOW),
                    self.assertRaisesRegex(ValueError, "expired memory"),
                ):
                    engine.supersede(old.id, content="must not revive")
                self.assertIs(engine._store.get(old.id).status, MemoryStatus.ACTIVE)
                self.assertEqual(
                    engine._store._connection.execute(
                        "SELECT COUNT(*) FROM memory_relations"
                    ).fetchone()[0],
                    0,
                )

    def test_ttl_cleanup_removes_replacement_at_original_deadline(self) -> None:
        with MemLiteEngine(self.database) as engine:
            with patch("memlite.manager.utc_now", return_value=NOW):
                old = engine.remember(
                    memory_type=MemoryType.WORKING,
                    scope_id="project:a",
                    content="database mysql",
                    ttl_seconds=120,
                )
                replacement = engine.supersede(old.id, content="database sqlite")
            with patch("memlite.storage.sqlite.utc_now", return_value=NOW + timedelta(seconds=120)):
                result = engine.run_eviction("project:a", policy=TTLEviction())
            self.assertEqual(result.evicted_ids, [replacement.id])
            self.assertIs(engine._store.get(replacement.id).status, MemoryStatus.DELETED)
            self.assertIs(engine._store.get(old.id).status, MemoryStatus.SUPERSEDED)
            self.assertEqual(
                engine._vector_index.search(
                    engine._embedding_provider.embed(["database sqlite"])[0],
                    scope_id="project:a",
                    model_id=engine._embedding_provider.model_id,
                ),
                [],
            )

    def test_correction_invalidates_only_affected_cache_and_replaces_vector(self) -> None:
        context = ScopeContext(model_id="offline")
        with MemLiteEngine(self.database) as engine:
            old = engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="project:a",
                content="database mysql",
            )
            for scope in ("project:a", "project:b"):
                engine.cache_store("database", "mysql", scope_id=scope, scope_context=context)
            replacement = engine.supersede(old.id, content="database sqlite")
            self.assertIsNone(replacement.expires_at)
            self.assertIs(
                engine.cache_lookup(
                    "database", scope_id="project:a", scope_context=context
                ).event_type,
                CacheEventType.MISS,
            )
            self.assertIs(
                engine.cache_lookup(
                    "database", scope_id="project:b", scope_context=context
                ).event_type,
                CacheEventType.HIT,
            )
            result = engine.retrieve("database sqlite", scope_id="project:a")
            self.assertEqual(result.selected_memory_ids, [replacement.id])
            hits = engine._vector_index.search(
                engine._embedding_provider.embed(["database sqlite"])[0],
                scope_id="project:a",
                model_id=engine._embedding_provider.model_id,
            )
            self.assertEqual([hit.memory_id for hit in hits], [replacement.id])

    def test_skill_correction_keeps_ttl_and_new_source_after_reopen(self) -> None:
        old = execute_request(
            self.database,
            {
                "operation": "remember",
                "scope": "project:a",
                "content": "SQLite database",
                "ttl_seconds": 3600,
            },
        )["memory"]
        replacement = execute_request(
            self.database,
            {
                "operation": "supersede",
                "scope": "project:a",
                "memory_id": old["id"],
                "content": "PostgreSQL database",
                "source": "tool",
                "source_ref": "確認過的設計紀錄",
            },
        )["memory"]
        self.assertEqual(replacement["expires_at"], old["expires_at"])
        with MemLiteEngine(self.database) as engine:
            saved = engine.get_memory(replacement["id"], scope_id="project:a")
            self.assertEqual(saved.to_dict(), replacement)
            self.assertIs(saved.source_type, SourceType.TOOL)
            self.assertEqual(saved.source_ref, "確認過的設計紀錄")
            self.assertIsNone(engine.get_memory(replacement["id"], scope_id="project:b"))

    def test_invalid_evidence_and_cross_scope_correction_leave_record_unchanged(self) -> None:
        old = execute_request(
            self.database,
            {"operation": "remember", "scope": "project:a", "content": "SQLite database"},
        )["memory"]
        for extra in ({"source_ref": 42}, {"source_ref": " "}, {"source": "unknown"}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                execute_request(
                    self.database,
                    {
                        "operation": "supersede",
                        "scope": "project:a",
                        "memory_id": old["id"],
                        "content": "PostgreSQL database",
                        **extra,
                    },
                )
        with self.assertRaises(LookupError):
            execute_request(
                self.database,
                {
                    "operation": "supersede",
                    "scope": "project:b",
                    "memory_id": old["id"],
                    "content": "wrong scope",
                },
            )
        current = execute_request(
            self.database,
            {"operation": "inspect", "scope": "project:a", "memory_id": old["id"]},
        )["memory"]
        self.assertEqual(current, old)
