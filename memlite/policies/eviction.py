"""Eviction policies that actively remove memories when capacity is exceeded.

The retrieval scoring module already uses recency and frequency as *ranking
signals*.  These eviction policies perform the complementary job of
**pruning** memories that exceed a capacity limit.

Supported strategies:
- TTL  — purge entries whose ``expires_at`` is in the past.
- LRU  — evict least-recently-accessed entries when count exceeds capacity.
- LFU  — evict least-frequently-accessed entries when count exceeds capacity.
- Hybrid — combine TTL purge + LRU/LFU capacity eviction in a single call.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from memlite.models import MemoryType
from memlite.storage.base import MemoryStore


class EvictionStrategy(StrEnum):
    TTL = "ttl"
    LRU = "lru"
    LFU = "lfu"


@dataclass(frozen=True, slots=True)
class EvictionResult:
    """Report of a single eviction run."""

    strategy: str
    scope_id: str
    evicted_ids: list[str]
    remaining_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "scope_id": self.scope_id,
            "evicted_count": len(self.evicted_ids),
            "evicted_ids": self.evicted_ids,
            "remaining_count": self.remaining_count,
        }


class EvictionPolicy(Protocol):
    """Protocol for pluggable eviction strategies."""

    def evict(
        self,
        store: MemoryStore,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
    ) -> EvictionResult: ...


class TTLEviction:
    """Purge all expired entries (entries whose ``expires_at`` <= now)."""

    def evict(
        self,
        store: MemoryStore,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
    ) -> EvictionResult:
        expired_items = store.list_expired(
            scope_id=scope_id, memory_types=memory_types, limit=100_000
        )
        evicted: list[str] = []
        for item in expired_items:
            store.soft_delete(item.id)
            evicted.append(item.id)

        remaining = store.list_active(
            scope_id=scope_id, memory_types=memory_types, limit=100_000
        )
        return EvictionResult(
            strategy=EvictionStrategy.TTL,
            scope_id=scope_id,
            evicted_ids=evicted,
            remaining_count=len(remaining),
        )


class LRUEviction:
    """Evict least-recently-accessed entries when count exceeds ``max_items``."""

    def __init__(self, max_items: int) -> None:
        if max_items < 1:
            raise ValueError("max_items must be at least 1")
        self._max_items = max_items

    @property
    def max_items(self) -> int:
        return self._max_items

    def evict(
        self,
        store: MemoryStore,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
    ) -> EvictionResult:
        candidates = store.list_active(
            scope_id=scope_id, memory_types=memory_types, limit=100_000
        )
        if len(candidates) <= self._max_items:
            return EvictionResult(
                strategy=EvictionStrategy.LRU,
                scope_id=scope_id,
                evicted_ids=[],
                remaining_count=len(candidates),
            )

        sorted_by_recency = sorted(
            candidates,
            key=lambda item: (item.last_accessed_at or item.created_at, item.importance),
        )

        to_evict = len(candidates) - self._max_items
        evicted: list[str] = []
        for item in sorted_by_recency:
            if len(evicted) >= to_evict:
                break
            store.soft_delete(item.id)
            evicted.append(item.id)

        return EvictionResult(
            strategy=EvictionStrategy.LRU,
            scope_id=scope_id,
            evicted_ids=evicted,
            remaining_count=len(candidates) - len(evicted),
        )


class LFUEviction:
    """Evict least-frequently-accessed entries when count exceeds ``max_items``."""

    def __init__(self, max_items: int) -> None:
        if max_items < 1:
            raise ValueError("max_items must be at least 1")
        self._max_items = max_items

    @property
    def max_items(self) -> int:
        return self._max_items

    def evict(
        self,
        store: MemoryStore,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
    ) -> EvictionResult:
        candidates = store.list_active(
            scope_id=scope_id, memory_types=memory_types, limit=100_000
        )
        if len(candidates) <= self._max_items:
            return EvictionResult(
                strategy=EvictionStrategy.LFU,
                scope_id=scope_id,
                evicted_ids=[],
                remaining_count=len(candidates),
            )

        sorted_by_frequency = sorted(
            candidates,
            key=lambda item: (item.access_count, item.importance),
        )

        to_evict = len(candidates) - self._max_items
        evicted: list[str] = []
        for item in sorted_by_frequency:
            if len(evicted) >= to_evict:
                break
            store.soft_delete(item.id)
            evicted.append(item.id)

        return EvictionResult(
            strategy=EvictionStrategy.LFU,
            scope_id=scope_id,
            evicted_ids=evicted,
            remaining_count=len(candidates) - len(evicted),
        )


class HybridEviction:
    """Run TTL purge first, then apply a capacity policy (LRU or LFU)."""

    def __init__(
        self,
        capacity_policy: LRUEviction | LFUEviction,
    ) -> None:
        self._ttl = TTLEviction()
        self._capacity = capacity_policy

    def evict(
        self,
        store: MemoryStore,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
    ) -> EvictionResult:
        ttl_result = self._ttl.evict(store, scope_id=scope_id, memory_types=memory_types)
        cap_result = self._capacity.evict(store, scope_id=scope_id, memory_types=memory_types)
        return EvictionResult(
            strategy=f"hybrid({cap_result.strategy})",
            scope_id=scope_id,
            evicted_ids=ttl_result.evicted_ids + cap_result.evicted_ids,
            remaining_count=cap_result.remaining_count,
        )
