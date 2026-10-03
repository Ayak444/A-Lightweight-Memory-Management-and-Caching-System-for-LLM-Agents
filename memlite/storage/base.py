from __future__ import annotations

from datetime import datetime
from typing import Protocol

from memlite.models import MemoryItem, MemoryType


class MemoryStore(Protocol):
    def save(self, item: MemoryItem, *, deduplicate: bool = True) -> MemoryItem: ...

    def get(self, memory_id: str) -> MemoryItem | None: ...

    def list_active(
        self,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
        limit: int = 20,
    ) -> list[MemoryItem]: ...

    def touch(self, memory_id: str, accessed_at: datetime) -> None: ...

    def replace(self, previous_id: str, replacement: MemoryItem) -> MemoryItem: ...

    def soft_delete(self, memory_id: str) -> bool: ...

    def list_expired(
        self,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
        limit: int = 10_000,
    ) -> list[MemoryItem]: ...

    def close(self) -> None: ...
