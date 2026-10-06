from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from memlite.embeddings.deterministic import DeterministicHashEmbedding
from memlite.evaluation.challenge_benchmark import (
    FIXED_NOW,
    STRATEGIES,
    evaluate_case,
    make_challenge_dataset,
)
from memlite.models import MemoryItem, MemoryStatus, MemoryType
from memlite.policies.retrieval import RetrievalConfig, RetrievalService
from memlite.storage.sqlite import SQLiteMemoryStore
from memlite.vector.base import VectorSearchHit


class RetrievalRefillTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(directory)
        self.store = SQLiteMemoryStore(self.root / "metadata.db")
        self.addCleanup(self.store.close)
        self.enterContext(patch("memlite.policies.retrieval.utc_now", return_value=FIXED_NOW))
        self.index = Mock()
        self.hits: list[VectorSearchHit] = []
        self.index.search.side_effect = lambda *args, **kwargs: self.hits[: kwargs["limit"]]

    def item(
        self,
        name: str,
        *,
        scope: str = "alpha",
        kind: MemoryType = MemoryType.SEMANTIC,
        expired: bool = False,
        status: MemoryStatus = MemoryStatus.ACTIVE,
    ) -> MemoryItem:
        item = MemoryItem(
            id=name,
            memory_type=kind,
            scope_id=scope,
            content=f"database {name}",
            status=status,
            created_at=FIXED_NOW - timedelta(days=1),
            updated_at=FIXED_NOW - timedelta(days=1),
            expires_at=FIXED_NOW if expired else None,
        )
        self.store.save(item, deduplicate=False)
        return item

    def service(self, **kwargs: object) -> RetrievalService:
        return RetrievalService(
            store=self.store,
            embedding_provider=DeterministicHashEmbedding(),
            vector_index=self.index,
            config=RetrievalConfig(**kwargs),
        )

    def test_real_sqlite_expired_candidates_do_not_hide_valid_fact(self) -> None:
        case = next(
            case
            for case in make_challenge_dataset()["cases"]
            if case["id"] == "evaluation-expired_candidates"
        )
        result = evaluate_case(case, STRATEGIES[3], self.root / "real.db")
        self.assertEqual(result["selected"], ["correct"])
        self.assertTrue(result["pass"])
        self.assertEqual(result["remaining_expired"], 25)
        self.assertEqual(result["evicted"], [])

    def test_refill_keeps_source_scope_type_status_and_expiry_authoritative(self) -> None:
        foreign = self.item("foreign", scope="beta")
        wrong_type = self.item("working", kind=MemoryType.WORKING)
        deleted = self.item("deleted", status=MemoryStatus.DELETED)
        expired = self.item("expired", expired=True)
        superseded = self.item("superseded", status=MemoryStatus.SUPERSEDED)
        first, second, third = [self.item(name) for name in ("first", "second", "third")]
        self.hits = [VectorSearchHit(item.id, 1.0) for item in (foreign, wrong_type)] + [
            VectorSearchHit("missing", 1.0),
            VectorSearchHit(deleted.id, 1.0),
            VectorSearchHit(expired.id, 1.0),
            VectorSearchHit(superseded.id, 1.0),
            VectorSearchHit(first.id, 0.9),
            VectorSearchHit(first.id, 0.9),
            VectorSearchHit(second.id, float("nan")),
            VectorSearchHit(second.id, 0.8),
            VectorSearchHit(third.id, float("inf")),
            VectorSearchHit(third.id, 0.7),
        ]
        response = self.service(candidate_limit=2).retrieve(
            "database", scope_id="alpha", memory_types={MemoryType.SEMANTIC}
        )
        self.assertEqual(response.selected_memory_ids, [first.id, second.id])
        self.assertEqual(
            {candidate.memory.id for candidate in response.candidates}, {first.id, second.id}
        )
        self.assertEqual(
            [call.kwargs["limit"] for call in self.index.search.call_args_list], [2, 4, 8, 16]
        )
        self.assertFalse(response.scan_limit_reached)
        for item in (foreign, wrong_type, deleted, expired, superseded, third):
            with self.subTest(item=item.id):
                self.assertEqual(self.store.get(item.id).access_count, 0)
        for item in (first, second):
            self.assertEqual(self.store.get(item.id).access_count, 1)

    def test_complete_valid_pool_does_not_refill_for_threshold_or_budget_rejections(self) -> None:
        first, second = self.item("first"), self.item("second")
        self.hits = [VectorSearchHit(first.id, 0.01), VectorSearchHit(second.id, 0.9)]
        response = self.service(candidate_limit=1).retrieve("database", scope_id="alpha")
        self.assertEqual(response.selected_memory_ids, [])
        self.assertEqual(response.candidates[0].rejection_reason, "below_similarity_threshold")
        self.index.search.assert_called_once()
        self.index.reset_mock()
        self.hits[0] = VectorSearchHit(first.id, 0.9)
        response = self.service(candidate_limit=1, token_budget=1).retrieve(
            "database", scope_id="alpha"
        )
        self.assertEqual(response.candidates[0].rejection_reason, "token_budget_exceeded")
        self.index.search.assert_called_once()

    def test_scan_cap_is_bounded_and_reported_without_deleting_or_touching_invalid_rows(
        self,
    ) -> None:
        expired = [self.item(f"expired-{i}", expired=True) for i in range(3)]
        valid = self.item("valid")
        self.hits = [VectorSearchHit(item.id, 1.0) for item in (*expired, valid)]
        response = self.service(candidate_limit=1, candidate_scan_limit=3).retrieve(
            "database", scope_id="alpha"
        )
        self.assertEqual(response.selected_memory_ids, [])
        self.assertTrue(response.scan_limit_reached)
        self.assertEqual(response.search_rounds, 3)
        self.assertEqual(response.search_limit, 3)
        self.assertEqual(response.scanned_hits, 3)
        self.assertTrue(response.to_dict()["scan_limit_reached"])
        self.assertEqual(
            [call.kwargs["limit"] for call in self.index.search.call_args_list], [1, 2, 3]
        )
        for item in (*expired, valid):
            saved = self.store.get(item.id)
            self.assertEqual(saved.status, MemoryStatus.ACTIVE)
            self.assertEqual(saved.access_count, 0)

    def test_exhausted_and_overproducing_backends_terminate_and_preserve_candidate_limit(
        self,
    ) -> None:
        expired = self.item("expired", expired=True)
        self.hits = [VectorSearchHit(expired.id, 1.0)]
        response = self.service(candidate_limit=2).retrieve("database", scope_id="alpha")
        self.assertEqual(response.search_rounds, 1)
        self.assertFalse(response.scan_limit_reached)
        valid = [self.item(f"valid-{i}") for i in range(4)]
        self.hits = [VectorSearchHit(item.id, 1.0) for item in valid]
        self.index.search.side_effect = lambda *args, **kwargs: self.hits
        response = self.service(candidate_limit=2).retrieve("database", scope_id="alpha")
        self.assertEqual(len(response.candidates), 2)
        self.assertEqual(response.selected_memory_ids, [valid[0].id, valid[1].id])

    def test_scan_limit_validation_and_empty_filter_short_circuit(self) -> None:
        for value in (0, -1, 1.5, True, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RetrievalConfig(candidate_limit=2, candidate_scan_limit=value)
        response = self.service().retrieve("database", scope_id="alpha", memory_types=set())
        self.assertEqual(response.search_rounds, 0)
        self.assertFalse(response.scan_limit_reached)
        self.index.search.assert_not_called()
