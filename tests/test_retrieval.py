from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memlite.embeddings.deterministic import DeterministicHashEmbedding
from memlite.engine import MemLiteEngine
from memlite.models import MemoryType
from memlite.policies.retrieval import RetrievalConfig


class RetrievalTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self._temporary_directory.name) / "memlite.db"

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_deterministic_embedding_is_stable_and_normalized(self) -> None:
        provider = DeterministicHashEmbedding(dimension=64)

        first = provider.embed(["回答請使用繁體中文"])[0]
        second = provider.embed(["回答請使用繁體中文"])[0]

        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0)

    def test_retrieval_returns_relevant_memory_with_score_trace(self) -> None:
        with MemLiteEngine(self.database_path) as engine:
            relevant = engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="project",
                content="回答時請使用繁體中文",
            )
            engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="project",
                content="部署環境使用 Docker",
            )

            response = engine.retrieve("我偏好使用哪一種中文？", scope_id="project")

        self.assertEqual(response.selected_memory_ids[0], relevant.id)
        self.assertGreater(response.candidates[0].score.similarity, 0)
        self.assertTrue(response.candidates[0].selected)

    def test_vector_index_survives_reopen(self) -> None:
        with MemLiteEngine(self.database_path) as engine:
            saved = engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="project",
                content="Semantic cache 使用可設定的 TTL",
            )

        with MemLiteEngine(self.database_path) as reopened:
            response = reopened.retrieve("快取 TTL", scope_id="project")

        self.assertIn(saved.id, response.selected_memory_ids)

    def test_retrieval_does_not_cross_scope(self) -> None:
        with MemLiteEngine(self.database_path) as engine:
            alpha = engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="alpha",
                content="Alpha 專案使用 Chroma",
            )
            beta = engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="beta",
                content="Beta 專案使用 Qdrant",
            )

            response = engine.retrieve("使用哪個 vector backend？", scope_id="alpha")

        self.assertIn(alpha.id, response.selected_memory_ids)
        self.assertNotIn(beta.id, [candidate.memory.id for candidate in response.candidates])

    def test_token_budget_records_rejection_reason(self) -> None:
        config = RetrievalConfig(token_budget=2, min_similarity=0.0)
        with MemLiteEngine(self.database_path, retrieval_config=config) as engine:
            engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="project",
                content="這是一段一定超過兩個 token 的記憶內容",
            )

            response = engine.retrieve("記憶內容", scope_id="project")

        self.assertEqual(response.selected_memory_ids, [])
        self.assertEqual(response.candidates[0].rejection_reason, "token_budget_exceeded")

    def test_superseded_memory_is_removed_from_vector_candidates(self) -> None:
        with MemLiteEngine(self.database_path) as engine:
            old = engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="project",
                content="部署區域是東京",
            )
            replacement = engine.supersede(old.id, content="部署區域已改為新加坡")

            response = engine.retrieve("目前的部署區域", scope_id="project")

        candidate_ids = [candidate.memory.id for candidate in response.candidates]
        self.assertIn(replacement.id, candidate_ids)
        self.assertNotIn(old.id, candidate_ids)


if __name__ == "__main__":
    unittest.main()
