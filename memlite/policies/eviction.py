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

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from memlite.models import MemoryItem, MemoryType
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
    protected_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "scope_id": self.scope_id,
            "evicted_count": len(self.evicted_ids),
            "evicted_ids": self.evicted_ids,
            "remaining_count": self.remaining_count,
            "protected_ids": self.protected_ids,
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


def _capacity_order(candidates: list[MemoryItem], strategy: EvictionStrategy) -> list[MemoryItem]:
    if strategy is EvictionStrategy.LRU:
        return sorted(
            candidates,
            key=lambda item: (item.last_accessed_at or item.created_at, item.importance),
        )
    return sorted(candidates, key=lambda item: (item.access_count, item.importance))


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

        remaining = store.list_active(scope_id=scope_id, memory_types=memory_types, limit=100_000)
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
        candidates = store.list_active(scope_id=scope_id, memory_types=memory_types, limit=100_000)
        if len(candidates) <= self._max_items:
            return EvictionResult(
                strategy=EvictionStrategy.LRU,
                scope_id=scope_id,
                evicted_ids=[],
                remaining_count=len(candidates),
            )

        sorted_by_recency = _capacity_order(candidates, EvictionStrategy.LRU)

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
        candidates = store.list_active(scope_id=scope_id, memory_types=memory_types, limit=100_000)
        if len(candidates) <= self._max_items:
            return EvictionResult(
                strategy=EvictionStrategy.LFU,
                scope_id=scope_id,
                evicted_ids=[],
                remaining_count=len(candidates),
            )

        sorted_by_frequency = _capacity_order(candidates, EvictionStrategy.LFU)

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


class ImportanceProtectedEviction:
    """Reserve bounded capacity for caller-rated importance, not verified truth.

    Unreserved records retain the wrapped policy's existing eviction order.
    Protection does not override expiry, scope, type, or total capacity.
    """

    def __init__(
        self,
        capacity_policy: LRUEviction | LFUEviction,
        *,
        importance_threshold: float = 0.8,
        confidence_threshold: float = 0.8,
        protected_slots: int = 1,
    ) -> None:
        if type(capacity_policy.max_items) is not int or capacity_policy.max_items < 1:
            raise ValueError("capacity must be a positive integer")
        if (
            type(protected_slots) is not int
            or not 0 <= protected_slots <= capacity_policy.max_items
        ):
            raise ValueError("protected_slots must be an integer between zero and capacity")
        for threshold in (importance_threshold, confidence_threshold):
            if (
                isinstance(threshold, bool)
                or not isinstance(threshold, (int, float))
                or not math.isfinite(threshold)
                or not 0.0 <= threshold <= 1.0
            ):
                raise ValueError(
                    "protection thresholds must be finite numbers between zero and one"
                )
        self._capacity_policy = capacity_policy
        self._importance_threshold = importance_threshold
        self._confidence_threshold = confidence_threshold
        self._protected_slots = protected_slots
        self._strategy = (
            EvictionStrategy.LRU
            if isinstance(capacity_policy, LRUEviction)
            else EvictionStrategy.LFU
        )

    @property
    def max_items(self) -> int:
        return self._capacity_policy.max_items

    def evict(
        self,
        store: MemoryStore,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
    ) -> EvictionResult:
        # Do not claim a hard capacity after acting on a truncated source list.
        candidates = store.list_active(scope_id=scope_id, memory_types=memory_types, limit=100_001)
        if len(candidates) > 100_000:
            raise ValueError("scope exceeds the protected policy's 100000-record snapshot limit")
        eligible = [
            item
            for item in candidates
            if item.importance >= self._importance_threshold
            and item.confidence >= self._confidence_threshold
        ]
        protected = sorted(
            eligible, key=lambda item: (-item.importance, -item.confidence, item.id)
        )[: self._protected_slots]
        protected_ids = {item.id for item in protected}
        order = _capacity_order(candidates, self._strategy)
        to_evict = max(0, len(candidates) - self.max_items)
        evicted: list[str] = []
        for item in order:
            if len(evicted) >= to_evict:
                break
            if item.id not in protected_ids and store.soft_delete(item.id):
                evicted.append(item.id)
        remaining = store.list_active(scope_id=scope_id, memory_types=memory_types, limit=100_001)
        return EvictionResult(
            strategy=f"protected({self._strategy})",
            scope_id=scope_id,
            evicted_ids=evicted,
            remaining_count=len(remaining),
            protected_ids=[item.id for item in protected],
        )


class HybridEviction:
    """Run TTL purge first, then apply a capacity policy (LRU or LFU)."""

    def __init__(
        self,
        capacity_policy: LRUEviction | LFUEviction | ImportanceProtectedEviction,
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
            protected_ids=cap_result.protected_ids,
        )
