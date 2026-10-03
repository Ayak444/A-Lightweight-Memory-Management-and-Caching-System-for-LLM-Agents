from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from memlite.manager import MemoryManager
from memlite.models import MemoryItem, MemoryStatus, MemoryType, utc_now
from memlite.storage.sqlite import SQLiteMemoryStore


class MemoryManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self._temporary_directory.name) / "memlite.db"
        self.manager = MemoryManager(SQLiteMemoryStore(self.database_path))

    def tearDown(self) -> None:
        self.manager.close()
        self._temporary_directory.cleanup()

    def test_memory_survives_store_reopen(self) -> None:
        saved = self.manager.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="student-1",
            content="Only use MIT or Apache-2.0 dependencies.",
        )
        self.manager.close()

        self.manager = MemoryManager(SQLiteMemoryStore(self.database_path))
        recalled = self.manager.recall(scope_id="student-1")

        self.assertEqual([item.id for item in recalled], [saved.id])
        self.assertEqual(recalled[0].access_count, 1)

    def test_scope_isolation(self) -> None:
        self.manager.remember(
            memory_type=MemoryType.WORKING,
            scope_id="alpha",
            content="Alpha-only context",
        )
        self.manager.remember(
            memory_type=MemoryType.WORKING,
            scope_id="beta",
            content="Beta-only context",
        )

        recalled = self.manager.recall(scope_id="alpha")

        self.assertEqual([item.content for item in recalled], ["Alpha-only context"])

    def test_duplicate_content_reuses_active_memory(self) -> None:
        first = self.manager.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="student-1",
            content="Prefer concise answers.",
        )
        duplicate = self.manager.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="student-1",
            content="  prefer   CONCISE answers. ",
        )

        self.assertEqual(first.id, duplicate.id)
        self.assertEqual(len(self.manager.recall(scope_id="student-1")), 1)

    def test_expired_memory_is_not_recalled(self) -> None:
        expired = MemoryItem(
            memory_type=MemoryType.WORKING,
            scope_id="student-1",
            content="Temporary scratchpad",
            expires_at=utc_now() - timedelta(seconds=1),
        )
        self.manager._store.save(expired)

        self.assertEqual(self.manager.recall(scope_id="student-1"), [])

    def test_supersede_hides_old_memory_and_records_replacement(self) -> None:
        old = self.manager.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="student-1",
            content="Deploy to Tokyo.",
        )

        replacement = self.manager.supersede(old.id, content="Deploy to Singapore.")
        recalled = self.manager.recall(scope_id="student-1")
        stored_old = self.manager._store.get(old.id)

        self.assertEqual([item.id for item in recalled], [replacement.id])
        self.assertIsNotNone(stored_old)
        self.assertEqual(stored_old.status, MemoryStatus.SUPERSEDED)


if __name__ == "__main__":
    unittest.main()
