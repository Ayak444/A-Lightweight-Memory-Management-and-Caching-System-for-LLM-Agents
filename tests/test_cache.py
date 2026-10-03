"""Tests for the semantic cache module."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memlite.cache import (
    CacheEventType,
    CacheStatus,
    ScopeContext,
    SemanticCache,
)
from memlite.embeddings.deterministic import DeterministicHashEmbedding
from memlite.engine import MemLiteEngine
from memlite.vector.sqlite import SQLiteVectorIndex


class SemanticCacheDirectTestCase(unittest.TestCase):
    """Tests against the SemanticCache service directly."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        base = Path(self._tmpdir.name)
        self._embedding = DeterministicHashEmbedding(dimension=64)
        self._vector = SQLiteVectorIndex(base / "cache_vectors.db")
        self._cache = SemanticCache(
            base / "cache.db",
            embedding_provider=self._embedding,
            vector_index=self._vector,
            similarity_threshold=0.15,
        )
        self._ctx = ScopeContext(model_id="test-model")

    def tearDown(self) -> None:
        self._cache.close()
        self._vector.close()
        self._tmpdir.cleanup()

    def test_exact_hit(self) -> None:
        """Identical query should produce an exact cache hit."""
        self._cache.store(
            "What license can I use?",
            "MIT or Apache-2.0",
            scope_id="demo",
            scope_context=self._ctx,
        )
        result = self._cache.lookup(
            "What license can I use?", scope_id="demo", scope_context=self._ctx
        )
        self.assertEqual(result.event_type, CacheEventType.HIT)
        self.assertIsNotNone(result.entry)
        self.assertEqual(result.entry.response, "MIT or Apache-2.0")
        self.assertAlmostEqual(result.similarity, 1.0)

    def test_semantic_hit(self) -> None:
        """Paraphrased query with shared tokens should hit via similarity."""
        # The deterministic hash embedding is lexical, so paraphrases must
        # share enough tokens to exceed the similarity threshold.
        self._cache.store(
            "Which open source licenses are allowed in this project?",
            "MIT or Apache-2.0 only",
            scope_id="demo",
            scope_context=self._ctx,
        )
        result = self._cache.lookup(
            "What open source licenses are allowed?",
            scope_id="demo",
            scope_context=self._ctx,
        )
        self.assertEqual(result.event_type, CacheEventType.HIT)
        self.assertIsNotNone(result.entry)
        self.assertGreater(result.similarity, 0.0)

    def test_miss_on_unrelated_query(self) -> None:
        """Completely unrelated query should miss."""
        self._cache.store(
            "Which database for metadata?",
            "SQLite",
            scope_id="demo",
            scope_context=self._ctx,
        )
        result = self._cache.lookup(
            "How to make coffee?", scope_id="demo", scope_context=self._ctx
        )
        self.assertEqual(result.event_type, CacheEventType.MISS)
        self.assertIsNone(result.entry)

    def test_scope_fingerprint_mismatch_rejects_hit(self) -> None:
        """Same query under different model should be rejected, not hit."""
        self._cache.store(
            "What is the deployment region?",
            "Tokyo",
            scope_id="demo",
            scope_context=ScopeContext(model_id="gpt-4"),
        )
        result = self._cache.lookup(
            "What is the deployment region?",
            scope_id="demo",
            scope_context=ScopeContext(model_id="gpt-3.5-turbo"),
        )
        # Either miss or rejected hit — never a valid hit
        self.assertNotEqual(result.event_type, CacheEventType.HIT)

    def test_ttl_expiration(self) -> None:
        """Expired entries should not be returned."""
        self._cache.store(
            "Temporary answer",
            "Expired response",
            scope_id="demo",
            scope_context=self._ctx,
            ttl_seconds=1,
        )
        # Manually expire it in the DB
        from memlite.models import utc_now
        from datetime import timedelta

        past = (utc_now() - timedelta(seconds=10)).isoformat()
        self._cache._conn.execute(
            "UPDATE cache_entries SET expires_at = ?", (past,)
        )
        self._cache._conn.commit()

        result = self._cache.lookup(
            "Temporary answer", scope_id="demo", scope_context=self._ctx
        )
        self.assertEqual(result.event_type, CacheEventType.MISS)

    def test_manual_invalidation(self) -> None:
        """Invalidated entries should not be returned."""
        entry = self._cache.store(
            "What is X?",
            "X is Y",
            scope_id="demo",
            scope_context=self._ctx,
        )
        self.assertTrue(self._cache.invalidate(entry.id))

        result = self._cache.lookup(
            "What is X?", scope_id="demo", scope_context=self._ctx
        )
        self.assertNotEqual(result.event_type, CacheEventType.HIT)

    def test_scope_invalidation(self) -> None:
        """invalidate_scope should clear all entries for a scope."""
        self._cache.store("Q1", "A1", scope_id="project-a", scope_context=self._ctx)
        self._cache.store("Q2", "A2", scope_id="project-a", scope_context=self._ctx)
        self._cache.store("Q3", "A3", scope_id="project-b", scope_context=self._ctx)

        count = self._cache.invalidate_scope("project-a")
        self.assertEqual(count, 2)

        # project-b should be unaffected
        remaining = self._cache.list_active("project-b")
        self.assertEqual(len(remaining), 1)

    def test_stats_tracking(self) -> None:
        """Stats should accurately track hits, misses, and stores."""
        self._cache.store("Q", "A", scope_id="demo", scope_context=self._ctx)
        self._cache.lookup("Q", scope_id="demo", scope_context=self._ctx)  # hit
        self._cache.lookup("Unknown query topic X Y Z", scope_id="demo", scope_context=self._ctx)  # miss

        stats = self._cache.stats()
        self.assertEqual(stats.active_entries, 1)
        self.assertGreaterEqual(stats.hits, 1)
        self.assertGreaterEqual(stats.misses, 1)
        self.assertGreater(stats.hit_rate, 0.0)
        self.assertLess(stats.hit_rate, 1.0)

    def test_access_count_increments(self) -> None:
        """Each hit should increment the entry's access_count."""
        self._cache.store("Q?", "A!", scope_id="demo", scope_context=self._ctx)
        self._cache.lookup("Q?", scope_id="demo", scope_context=self._ctx)
        self._cache.lookup("Q?", scope_id="demo", scope_context=self._ctx)

        entries = self._cache.list_active("demo")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].access_count, 2)


class EngineCacheIntegrationTestCase(unittest.TestCase):
    """Tests cache operations through the MemLiteEngine facade."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "memlite.db"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_cache_roundtrip_through_engine(self) -> None:
        """Store and lookup cache through the engine."""
        ctx = ScopeContext(model_id="test")
        with MemLiteEngine(self.db_path, cache_similarity_threshold=0.50) as engine:
            engine.cache_store(
                "What is the metadata DB?",
                "SQLite",
                scope_id="project",
                scope_context=ctx,
            )
            result = engine.cache_lookup(
                "What is the metadata DB?",
                scope_id="project",
                scope_context=ctx,
            )
        self.assertEqual(result.event_type, CacheEventType.HIT)
        self.assertEqual(result.entry.response, "SQLite")

    def test_cache_stats_through_engine(self) -> None:
        """Stats should reflect operations."""
        ctx = ScopeContext(model_id="test")
        with MemLiteEngine(self.db_path) as engine:
            engine.cache_store("Q", "A", scope_id="s", scope_context=ctx)
            stats = engine.cache_stats()
        self.assertEqual(stats.total_entries, 1)

    def test_cache_invalidate_through_engine(self) -> None:
        """Invalidation through engine should work."""
        ctx = ScopeContext(model_id="test")
        with MemLiteEngine(self.db_path, cache_similarity_threshold=0.50) as engine:
            entry = engine.cache_store("Q", "A", scope_id="s", scope_context=ctx)
            self.assertTrue(engine.cache_invalidate(entry.id))
            result = engine.cache_lookup("Q", scope_id="s", scope_context=ctx)
        self.assertNotEqual(result.event_type, CacheEventType.HIT)


if __name__ == "__main__":
    unittest.main()
