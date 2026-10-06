from __future__ import annotations

from datetime import timedelta

from memlite.models import MemoryItem, MemoryStatus, MemoryType, SourceType, utc_now
from memlite.storage.base import MemoryStore


class MemoryNotFoundError(LookupError):
    pass


class MemoryManager:
    """Coordinates memory lifecycle rules without depending on a storage backend."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def remember(
        self,
        *,
        memory_type: MemoryType,
        scope_id: str,
        content: str,
        source_type: SourceType = SourceType.USER,
        source_ref: str | None = None,
        importance: float = 0.5,
        confidence: float = 1.0,
        ttl_seconds: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> MemoryItem:
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")

        now = utc_now()
        item = MemoryItem(
            memory_type=memory_type,
            scope_id=scope_id,
            content=content,
            source_type=source_type,
            source_ref=source_ref,
            importance=importance,
            confidence=confidence,
            expires_at=now + timedelta(seconds=ttl_seconds) if ttl_seconds else None,
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        return self._store.save(item, deduplicate=True)

    def recall(
        self,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
        limit: int = 20,
    ) -> list[MemoryItem]:
        if limit < 1:
            raise ValueError("limit must be at least one")

        items = self._store.list_active(
            scope_id=scope_id,
            memory_types=memory_types,
            limit=limit,
        )
        recalled_at = utc_now()
        for item in items:
            self._store.touch(item.id, recalled_at)
            item.last_accessed_at = recalled_at
            item.access_count += 1
        return items

    def supersede(
        self,
        memory_id: str,
        *,
        content: str,
        source_type: SourceType = SourceType.USER,
        source_ref: str | None = None,
        importance: float | None = None,
        confidence: float | None = None,
        metadata: dict[str, object] | None = None,
    ) -> MemoryItem:
        previous = self._store.get(memory_id)
        if previous is None or previous.status is not MemoryStatus.ACTIVE:
            raise MemoryNotFoundError(f"active memory not found: {memory_id}")

        now = utc_now()
        if previous.is_expired(now):
            raise ValueError("expired memory cannot be superseded; create a new memory")
        replacement = MemoryItem(
            memory_type=previous.memory_type,
            scope_id=previous.scope_id,
            content=content,
            source_type=source_type,
            source_ref=source_ref,
            importance=previous.importance if importance is None else importance,
            confidence=previous.confidence if confidence is None else confidence,
            expires_at=previous.expires_at,
            metadata=dict(previous.metadata if metadata is None else metadata),
            created_at=now,
            updated_at=now,
        )
        return self._store.replace(memory_id, replacement)

    def forget(self, memory_id: str) -> bool:
        return self._store.soft_delete(memory_id)

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> MemoryManager:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
