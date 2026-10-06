"""Tests for eviction policies."""

from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from memlite.engine import MemLiteEngine
from memlite.manager import MemoryManager
from memlite.models import MemoryItem, MemoryType, utc_now
from memlite.policies.eviction import (
    HybridEviction,
    LFUEviction,
    LRUEviction,
    TTLEviction,
)
from memlite.storage.sqlite import SQLiteMemoryStore


class TTLEvictionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._store = SQLiteMemoryStore(Path(self._tmpdir.name) / "test.db")
        self._manager = MemoryManager(self._store)

    def tearDown(self) -> None:
        self._store.close()
        self._tmpdir.cleanup()

    def test_ttl_evicts_expired_entries(self) -> None:
        """Expired entries should be soft-deleted."""
        # Create an expired memory
        expired = MemoryItem(
            memory_type=MemoryType.WORKING,
            scope_id="test",
            content="Expired scratchpad",
            expires_at=utc_now() - timedelta(seconds=10),
        )
        self._store.save(expired)

        # Create a non-expired memory
        self._manager.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="test",
            content="Valid memory",
        )

        policy = TTLEviction()
        result = policy.evict(self._store, scope_id="test")

        self.assertEqual(len(result.evicted_ids), 1)
        self.assertIn(expired.id, result.evicted_ids)
        self.assertEqual(result.remaining_count, 1)

    def test_ttl_no_expired_entries(self) -> None:
        """No eviction when nothing is expired."""
        self._manager.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="test",
            content="Valid memory",
        )
        result = TTLEviction().evict(self._store, scope_id="test")
        self.assertEqual(len(result.evicted_ids), 0)
        self.assertEqual(result.remaining_count, 1)


class LRUEvictionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._store = SQLiteMemoryStore(Path(self._tmpdir.name) / "test.db")
        self._manager = MemoryManager(self._store)

    def tearDown(self) -> None:
        self._store.close()
        self._tmpdir.cleanup()

    def test_lru_evicts_least_recently_accessed(self) -> None:
        """Oldest accessed items should be evicted first when over capacity."""
        # Create 5 memories, only touch the last 2
        items = []
        for i in range(5):
            item = self._manager.remember(
                memory_type=MemoryType.EPISODIC,
                scope_id="test",
                content=f"Memory item number {i} for testing",
            )
            items.append(item)

        # Touch items 3 and 4 to make them "recently used"
        now = utc_now()
        self._store.touch(items[3].id, now)
        self._store.touch(items[4].id, now)

        policy = LRUEviction(max_items=2)
        result = policy.evict(self._store, scope_id="test")

        self.assertEqual(len(result.evicted_ids), 3)
        self.assertEqual(result.remaining_count, 2)
        # The recently touched items should survive
        remaining = self._store.list_active(scope_id="test")
        remaining_ids = {item.id for item in remaining}
        self.assertIn(items[3].id, remaining_ids)
        self.assertIn(items[4].id, remaining_ids)

    def test_lru_no_eviction_under_capacity(self) -> None:
        """No eviction when count is at or below capacity."""
        self._manager.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="test",
            content="Only item",
        )
        result = LRUEviction(max_items=5).evict(self._store, scope_id="test")
        self.assertEqual(len(result.evicted_ids), 0)

    def test_lru_max_items_validation(self) -> None:
        with self.assertRaises(ValueError):
            LRUEviction(max_items=0)


class LFUEvictionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._store = SQLiteMemoryStore(Path(self._tmpdir.name) / "test.db")
        self._manager = MemoryManager(self._store)

    def tearDown(self) -> None:
        self._store.close()
        self._tmpdir.cleanup()

    def test_lfu_evicts_least_frequently_accessed(self) -> None:
        """Items with lowest access count should be evicted first."""
        items = []
        for i in range(4):
            item = self._manager.remember(
                memory_type=MemoryType.EPISODIC,
                scope_id="test",
                content=f"LFU test memory {i} unique content here",
            )
            items.append(item)

        # Touch items 0 and 1 multiple times
        now = utc_now()
        for _ in range(5):
            self._store.touch(items[0].id, now)
        for _ in range(3):
            self._store.touch(items[1].id, now)
        # items[2] and items[3] have 0 access

        policy = LFUEviction(max_items=2)
        result = policy.evict(self._store, scope_id="test")

        self.assertEqual(len(result.evicted_ids), 2)
        self.assertEqual(result.remaining_count, 2)
        # The frequently accessed items should survive
        remaining = self._store.list_active(scope_id="test")
        remaining_ids = {item.id for item in remaining}
        self.assertIn(items[0].id, remaining_ids)
        self.assertIn(items[1].id, remaining_ids)


class HybridEvictionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._store = SQLiteMemoryStore(Path(self._tmpdir.name) / "test.db")
        self._manager = MemoryManager(self._store)

    def tearDown(self) -> None:
        self._store.close()
        self._tmpdir.cleanup()

    def test_hybrid_ttl_then_lru(self) -> None:
        """Hybrid should first purge TTL, then apply LRU."""
        # Add an expired entry
        expired = MemoryItem(
            memory_type=MemoryType.WORKING,
            scope_id="test",
            content="Expired hybrid test memory",
            expires_at=utc_now() - timedelta(seconds=10),
        )
        self._store.save(expired)

        # Add 3 non-expired
        for i in range(3):
            self._manager.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="test",
                content=f"Hybrid test memory {i} persistent",
            )

        policy = HybridEviction(LRUEviction(max_items=2))
        result = policy.evict(self._store, scope_id="test")

        # TTL should evict the expired one, LRU should evict 1 more to get to 2
        self.assertIn(expired.id, result.evicted_ids)
        self.assertEqual(result.remaining_count, 2)


class EngineEvictionIntegrationTestCase(unittest.TestCase):
    """Tests eviction through the MemLiteEngine facade."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "memlite.db"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_eviction_removes_vectors_too(self) -> None:
        """Engine eviction should also clean up vector index entries."""
        policy = LRUEviction(max_items=1)
        with MemLiteEngine(self.db_path, eviction_policy=policy) as engine:
            engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="test",
                content="First memory to be evicted eventually",
            )
            kept = engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="test",
                content="Second memory which is newer",
            )

            result = engine.run_eviction("test")

            self.assertEqual(result.remaining_count, 1)
            # The kept item should still be retrievable
            response = engine.retrieve("Second memory", scope_id="test")
            selected_ids = response.selected_memory_ids
            self.assertIn(kept.id, selected_ids)

    def test_eviction_without_policy_raises(self) -> None:
        """Calling run_eviction without a policy should raise ValueError."""
        with MemLiteEngine(self.db_path) as engine:
            engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="test",
                content="Some content",
            )
            with self.assertRaises(ValueError):
                engine.run_eviction("test")


if __name__ == "__main__":
    unittest.main()
