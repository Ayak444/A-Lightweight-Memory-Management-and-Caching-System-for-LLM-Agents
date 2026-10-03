from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from memlite.embeddings.deterministic import DeterministicHashEmbedding
from memlite.manager import MemoryManager
from memlite.models import MemoryType
from memlite.policies.retrieval import RetrievalConfig, RetrievalService
from memlite.storage.sqlite import SQLiteMemoryStore
from memlite.vector.base import VectorSearchHit
from memlite.vector.sqlite import SQLiteVectorIndex


class RetrievalBoundaryTests(unittest.TestCase):
    def test_untrusted_index_hits_are_filtered_before_scoring_or_touch(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        store = SQLiteMemoryStore(Path(directory) / "metadata.db")
        self.addCleanup(store.close)
        manager = MemoryManager(store)
        allowed, foreign, wrong_type = [
            manager.remember(memory_type=kind, scope_id=scope, content="private memory")
            for scope, kind in [
                ("alpha", MemoryType.SEMANTIC),
                ("beta", MemoryType.SEMANTIC),
                ("alpha", MemoryType.WORKING),
            ]
        ]
        index = Mock()
        index.search.return_value = [
            VectorSearchHit(foreign.id, 1.0),
            VectorSearchHit(wrong_type.id, 1.0),
            VectorSearchHit(allowed.id, float("nan")),
            VectorSearchHit(allowed.id, float("inf")),
            VectorSearchHit(allowed.id, 0.9),
            VectorSearchHit(allowed.id, 0.9),
        ]
        service = RetrievalService(
            store=store, embedding_provider=DeterministicHashEmbedding(), vector_index=index
        )
        response = service.retrieve(
            "memory", scope_id="alpha", memory_types={MemoryType.SEMANTIC}
        )
        self.assertEqual([c.memory.id for c in response.candidates], [allowed.id])
        self.assertEqual(response.selected_memory_ids, [allowed.id])
        for item, expected_count in [(allowed, 1), (foreign, 0), (wrong_type, 0)]:
            saved = store.get(item.id)
            assert saved is not None
            self.assertEqual(saved.access_count, expected_count)

    def test_empty_type_filter_matches_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMemoryStore(Path(directory) / "metadata.db")
            index = SQLiteVectorIndex(Path(directory) / "vectors.db")
            try:
                item = MemoryManager(store).remember(
                    memory_type=MemoryType.SEMANTIC, scope_id="alpha", content="memory"
                )
                index.upsert(
                    memory_id=item.id, scope_id="alpha", memory_type=item.memory_type,
                    model_id="test", vector=[1.0],
                )
                self.assertEqual(store.list_active(scope_id="alpha", memory_types=set()), [])
                self.assertEqual(index.search(
                    [1.0], scope_id="alpha", model_id="test", memory_types=set()
                ), [])
                self.assertEqual(len(store.list_active(scope_id="alpha")), 1)
            finally:
                index.close()
                store.close()

    def test_invalid_scoring_settings_fail_early(self) -> None:
        for value in [float("nan"), float("inf"), -0.1, 1.1]:
            with self.subTest(min_similarity=value), self.assertRaises(ValueError):
                RetrievalConfig(min_similarity=value)
        for value in [float("nan"), float("inf"), 0.0, -1.0]:
            with self.subTest(half_life=value), self.assertRaises(ValueError):
                RetrievalConfig(recency_half_life_days=value)
        with self.assertRaises(ValueError):
            RetrievalConfig(similarity_weight=-0.1, recency_weight=0.8)

    def test_zero_weight_ablation_is_supported(self) -> None:
        config = RetrievalConfig(
            similarity_weight=1.0, recency_weight=0.0, importance_weight=0.0,
            confidence_weight=0.0, frequency_weight=0.0,
        )
        self.assertEqual(config.similarity_weight, 1.0)
