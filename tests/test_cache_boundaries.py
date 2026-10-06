from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memlite.cache import CacheEventType, ScopeContext, SemanticCache
from memlite.embeddings.deterministic import DeterministicHashEmbedding
from memlite.vector.base import VectorSearchHit
from memlite.vector.sqlite import SQLiteVectorIndex


class CacheBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        self.index = SQLiteVectorIndex(path / "vectors.db")
        self.addCleanup(self.index.close)
        self.cache = SemanticCache(
            path / "cache.db",
            embedding_provider=DeterministicHashEmbedding(),
            vector_index=self.index,
        )
        self.addCleanup(self.cache.close)

    def test_wrong_context_does_not_mask_later_valid_semantic_candidate(self) -> None:
        wrong = self.cache.store(
            "Project database", "Old", scope_id="user", scope_context=ScopeContext(model_id="a")
        )
        valid = self.cache.store(
            "Project database", "New", scope_id="user", scope_context=ScopeContext(model_id="b")
        )
        with patch.object(
            self.index,
            "search",
            return_value=[
                VectorSearchHit(wrong.id, 0.99),
                VectorSearchHit(valid.id, 0.98),
            ],
        ):
            result = self.cache.lookup(
                "What database?", scope_id="user", scope_context=ScopeContext(model_id="b")
            )
        self.assertEqual(result.event_type, CacheEventType.HIT)
        self.assertIsNotNone(result.entry)
        assert result.entry is not None
        self.assertEqual(result.entry.response, "New")

    def test_cross_scope_and_non_finite_hits_are_not_trusted(self) -> None:
        entry = self.cache.store(
            "Private database", "Secret", scope_id="private", scope_context=ScopeContext()
        )
        local = self.cache.store(
            "Database", "SQLite", scope_id="user", scope_context=ScopeContext()
        )
        with patch.object(
            self.index,
            "search",
            return_value=[
                VectorSearchHit(entry.id, 1.0),
                VectorSearchHit(local.id, float("nan")),
            ],
        ):
            result = self.cache.lookup(
                "What database?", scope_id="user", scope_context=ScopeContext()
            )
        self.assertEqual(result.event_type, CacheEventType.MISS)
        self.assertIsNone(result.entry)

    def test_invalid_ttl_does_not_create_entry(self) -> None:
        for ttl in (0, -1):
            with self.assertRaises(ValueError):
                self.cache.store(
                    "Q", "A", scope_id="user", scope_context=ScopeContext(), ttl_seconds=ttl
                )
        self.assertEqual(self.cache.stats().total_entries, 0)
