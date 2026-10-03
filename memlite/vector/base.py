from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from memlite.models import MemoryType


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    memory_id: str
    similarity: float


class VectorIndex(Protocol):
    def upsert(
        self,
        *,
        memory_id: str,
        scope_id: str,
        memory_type: MemoryType,
        model_id: str,
        vector: list[float],
    ) -> None: ...

    def delete(self, memory_id: str) -> None: ...

    def clear_scope(self, scope_id: str) -> None: ...

    def search(
        self,
        vector: list[float],
        *,
        scope_id: str,
        model_id: str,
        memory_types: set[MemoryType] | None = None,
        limit: int = 20,
    ) -> list[VectorSearchHit]: ...

    def close(self) -> None: ...
