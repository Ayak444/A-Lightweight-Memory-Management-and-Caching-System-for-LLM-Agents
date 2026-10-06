from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from memlite.engine import MemLiteEngine
from memlite.evaluation.challenge_benchmark import FIXED_NOW
from memlite.models import MemoryItem, MemoryStatus, MemoryType
from memlite.policies.eviction import (
    HybridEviction,
    ImportanceProtectedEviction,
    LFUEviction,
    LRUEviction,
)
from memlite.storage.sqlite import SQLiteMemoryStore


class ProtectedEvictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store = SQLiteMemoryStore(self.root / "metadata.db")
        self.addCleanup(self.store.close)
        self.enterContext(patch("memlite.storage.sqlite.utc_now", return_value=FIXED_NOW))

    def item(
        self,
        name: str,
        *,
        importance: float = 0.5,
        confidence: float = 1.0,
        age: int = 1,
        frequency: int = 10,
        scope: str = "alpha",
        kind: MemoryType = MemoryType.SEMANTIC,
        expired: bool = False,
    ) -> MemoryItem:
        time = FIXED_NOW - timedelta(days=age)
        item = MemoryItem(
            id=name,
            scope_id=scope,
            memory_type=kind,
            content=f"database {name}",
            importance=importance,
            confidence=confidence,
            created_at=time,
            updated_at=time,
            last_accessed_at=time,
            access_count=frequency,
            expires_at=FIXED_NOW if expired else None,
        )
        self.store.save(item, deduplicate=False)
        return item

    def test_protection_preserves_cold_important_record_within_capacity(self) -> None:
        for base in (LRUEviction, LFUEviction):
            scope = base.__name__
            with self.subTest(base=scope):
                important = self.item(
                    f"{scope}-important", scope=scope, importance=1.0, age=90, frequency=0
                )
                for i in range(5):
                    self.item(f"{scope}-noise-{i}", scope=scope)
                result = ImportanceProtectedEviction(base(2)).evict(self.store, scope_id=scope)
                self.assertEqual(result.protected_ids, [important.id])
                self.assertEqual(result.remaining_count, 2)
                self.assertEqual(len(result.evicted_ids), 4)
                self.assertEqual(self.store.get(important.id).status, MemoryStatus.ACTIVE)
                self.assertEqual(self.store.get(important.id).access_count, 0)
                self.assertEqual(result.to_dict()["protected_ids"], [important.id])

    def test_zero_slots_and_no_qualifying_records_preserve_baseline_order(self) -> None:
        for base in (LRUEviction, LFUEviction):
            for slots, importance in ((0, 1.0), (1, 0.7)):
                with self.subTest(base=base.__name__, slots=slots):
                    scope = f"{base.__name__}-{slots}"
                    for suffix in ("before", "after"):
                        for i in range(4):
                            self.item(
                                f"{scope}-{suffix}-{i}",
                                scope=f"{scope}-{suffix}",
                                importance=importance,
                                age=i + 1,
                                frequency=i,
                            )
                    before = base(2).evict(self.store, scope_id=f"{scope}-before")
                    after = ImportanceProtectedEviction(base(2), protected_slots=slots).evict(
                        self.store, scope_id=f"{scope}-after"
                    )
                    self.assertEqual(
                        [name.rsplit("-", 1)[1] for name in before.evicted_ids],
                        [name.rsplit("-", 1)[1] for name in after.evicted_ids],
                    )
                    self.assertEqual(after.protected_ids, [])

    def test_overflow_of_eligible_records_reserves_one_slot_not_unbounded_pins(self) -> None:
        for name in ("c", "b", "a"):
            self.item(name, importance=1.0, age=90, frequency=0)
        for i in range(4):
            self.item(f"noise-{i}")
        result = ImportanceProtectedEviction(LRUEviction(2)).evict(self.store, scope_id="alpha")
        self.assertEqual(result.protected_ids, ["a"])
        self.assertEqual(result.remaining_count, 2)
        self.assertEqual(len(result.evicted_ids), 5)
        self.assertIn("b", result.evicted_ids)
        self.assertIn("c", result.evicted_ids)

    def test_scope_type_confidence_and_expiry_cannot_be_overridden_by_importance(self) -> None:
        excluded = [
            self.item("foreign", scope="beta", importance=1.0),
            self.item("working", kind=MemoryType.WORKING, importance=1.0),
            self.item("expired", importance=1.0, expired=True),
        ]
        uncertain = self.item("uncertain", importance=1.0, confidence=0.2, age=90, frequency=0)
        self.item("valid")
        result = ImportanceProtectedEviction(LRUEviction(1)).evict(
            self.store, scope_id="alpha", memory_types={MemoryType.SEMANTIC}
        )
        self.assertEqual(result.protected_ids, [])
        self.assertEqual(result.evicted_ids, [uncertain.id])
        for item in excluded:
            self.assertEqual(self.store.get(item.id).status, MemoryStatus.ACTIVE)

    def test_hybrid_ttl_removes_expired_important_record_before_capacity_protection(self) -> None:
        expired = self.item("expired", expired=True, importance=1.0)
        important = self.item("important", importance=1.0, age=90, frequency=0)
        for i in range(3):
            self.item(f"noise-{i}")
        result = HybridEviction(ImportanceProtectedEviction(LFUEviction(2))).evict(
            self.store, scope_id="alpha"
        )
        self.assertIn(expired.id, result.evicted_ids)
        self.assertEqual(result.protected_ids, [important.id])
        self.assertEqual(result.remaining_count, 2)

    def test_under_capacity_and_empty_filter_do_not_delete(self) -> None:
        important = self.item("important", importance=1.0)
        policy = ImportanceProtectedEviction(LRUEviction(2))
        result = policy.evict(self.store, scope_id="alpha")
        self.assertEqual(result.evicted_ids, [])
        self.assertEqual(result.protected_ids, [important.id])
        empty = policy.evict(self.store, scope_id="alpha", memory_types=set())
        self.assertEqual(empty.remaining_count, 0)
        self.assertEqual(empty.protected_ids, [])

    def test_invalid_threshold_quota_and_capacity_fail_early(self) -> None:
        for field in ("importance_threshold", "confidence_threshold"):
            for value in (float("nan"), float("inf"), -0.1, 1.1, True, "0.8"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    ImportanceProtectedEviction(LRUEviction(2), **{field: value})
        for value in (-1, 3, 0.5, True):
            with self.subTest(slots=value), self.assertRaises(ValueError):
                ImportanceProtectedEviction(LRUEviction(2), protected_slots=value)
        with self.assertRaises(ValueError):
            ImportanceProtectedEviction(LRUEviction(True))

    def test_oversized_snapshot_fails_before_mutating(self) -> None:
        store = Mock()
        store.list_active.return_value = [self.item("important", importance=1.0)] * 100_001
        with self.assertRaises(ValueError):
            ImportanceProtectedEviction(LRUEviction(2)).evict(store, scope_id="alpha")
        store.soft_delete.assert_not_called()

    def test_engine_keeps_protected_vector_and_invalidates_only_affected_cache(self) -> None:
        with MemLiteEngine(self.root / "engine.db") as engine:
            important = engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="alpha",
                content="critical database recovery",
                importance=1.0,
            )
            noise = engine.remember(
                memory_type=MemoryType.SEMANTIC, scope_id="alpha", content="daily meeting"
            )
            engine.cache_store("database", "old answer", scope_id="alpha")
            engine.cache_store("database", "other scope", scope_id="beta")
            result = engine.run_eviction(
                "alpha", policy=ImportanceProtectedEviction(LRUEviction(1))
            )
            self.assertEqual(result.protected_ids, [important.id])
            self.assertEqual(result.evicted_ids, [noise.id])
            self.assertEqual(engine.cache_list("alpha"), [])
            self.assertEqual(len(engine.cache_list("beta")), 1)
            response = engine.retrieve("critical database recovery", scope_id="alpha")
            self.assertEqual(response.selected_memory_ids, [important.id])
            self.assertNotIn(noise.id, [candidate.memory.id for candidate in response.candidates])
