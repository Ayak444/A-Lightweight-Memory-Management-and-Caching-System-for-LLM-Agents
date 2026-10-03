from __future__ import annotations

from pathlib import Path

from memlite.cache import CacheLookupResult, CacheEntry, CacheStats, SemanticCache, ScopeContext
from memlite.embeddings.base import EmbeddingProvider
from memlite.embeddings.deterministic import DeterministicHashEmbedding
from memlite.manager import MemoryManager
from memlite.models import MemoryItem, MemoryType, SourceType
from memlite.policies.eviction import (
    EvictionPolicy,
    EvictionResult,
    HybridEviction,
    LFUEviction,
    LRUEviction,
    TTLEviction,
)
from memlite.policies.retrieval import RetrievalConfig, RetrievalResponse, RetrievalService
from memlite.storage.sqlite import SQLiteMemoryStore
from memlite.vector.base import VectorIndex
from memlite.vector.sqlite import SQLiteVectorIndex


class MemLiteEngine:
    """High-level facade that keeps metadata, vector retrieval, cache and eviction synchronized."""

    def __init__(
        self,
        metadata_path: str | Path,
        *,
        vector_path: str | Path | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        vector_index: VectorIndex | None = None,
        retrieval_config: RetrievalConfig | None = None,
        cache_similarity_threshold: float = 0.85,
        cache_default_ttl_seconds: int | None = None,
        eviction_policy: EvictionPolicy | None = None,
    ) -> None:
        metadata_path = Path(metadata_path)
        self._store = SQLiteMemoryStore(metadata_path)
        self._manager = MemoryManager(self._store)
        self._embedding_provider = embedding_provider or DeterministicHashEmbedding()
        self._vector_index = vector_index or SQLiteVectorIndex(
            vector_path or metadata_path.with_name(f"{metadata_path.stem}.vectors.db")
        )
        self._retrieval = RetrievalService(
            store=self._store,
            embedding_provider=self._embedding_provider,
            vector_index=self._vector_index,
            config=retrieval_config,
        )
        self._cache_vector_index = SQLiteVectorIndex(
            metadata_path.with_name(f"{metadata_path.stem}.cache_vectors.db")
        )
        self._cache = SemanticCache(
            metadata_path.with_name(f"{metadata_path.stem}.cache.db"),
            embedding_provider=self._embedding_provider,
            vector_index=self._cache_vector_index,
            similarity_threshold=cache_similarity_threshold,
            default_ttl_seconds=cache_default_ttl_seconds,
        )
        self._eviction_policy = eviction_policy

    # -- Memory operations --

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
        item = self._manager.remember(
            memory_type=memory_type,
            scope_id=scope_id,
            content=content,
            source_type=source_type,
            source_ref=source_ref,
            importance=importance,
            confidence=confidence,
            ttl_seconds=ttl_seconds,
            metadata=metadata,
        )
        self._index(item)
        return item

    def retrieve(
        self,
        query: str,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
    ) -> RetrievalResponse:
        return self._retrieval.retrieve(
            query,
            scope_id=scope_id,
            memory_types=memory_types,
        )

    def supersede(self, memory_id: str, *, content: str) -> MemoryItem:
        replacement = self._manager.supersede(memory_id, content=content)
        self._vector_index.delete(memory_id)
        self._index(replacement)
        return replacement

    def forget(self, memory_id: str) -> bool:
        deleted = self._manager.forget(memory_id)
        if deleted:
            self._vector_index.delete(memory_id)
        return deleted

    def reindex_scope(self, scope_id: str) -> int:
        self._vector_index.clear_scope(scope_id)
        memories = self._store.list_active(scope_id=scope_id, limit=100_000)
        for memory in memories:
            self._index(memory)
        return len(memories)

    # -- Cache operations --

    def cache_lookup(
        self,
        query: str,
        *,
        scope_id: str,
        scope_context: ScopeContext | None = None,
    ) -> CacheLookupResult:
        """Try to find a cached response for the given query."""
        ctx = scope_context or ScopeContext()
        return self._cache.lookup(query, scope_id=scope_id, scope_context=ctx)

    def cache_store(
        self,
        query: str,
        response: str,
        *,
        scope_id: str,
        scope_context: ScopeContext | None = None,
        ttl_seconds: int | None = None,
    ) -> CacheEntry:
        """Store a query-response pair in the semantic cache."""
        ctx = scope_context or ScopeContext()
        return self._cache.store(
            query,
            response,
            scope_id=scope_id,
            scope_context=ctx,
            ttl_seconds=ttl_seconds,
        )

    def cache_invalidate(self, cache_id: str) -> bool:
        """Manually invalidate a specific cache entry."""
        return self._cache.invalidate(cache_id)

    def cache_invalidate_scope(self, scope_id: str) -> int:
        """Invalidate all cache entries for a scope."""
        return self._cache.invalidate_scope(scope_id)

    def cache_stats(self) -> CacheStats:
        """Return aggregate cache statistics."""
        return self._cache.stats()

    def cache_list(self, scope_id: str, *, limit: int = 50) -> list[CacheEntry]:
        """List active cache entries for inspection."""
        return self._cache.list_active(scope_id, limit=limit)

    # -- Eviction operations --

    def run_eviction(
        self,
        scope_id: str,
        *,
        memory_types: set[MemoryType] | None = None,
        policy: EvictionPolicy | None = None,
    ) -> EvictionResult:
        """Run the configured or provided eviction policy on a scope.

        Any evicted memories are also removed from the vector index.
        """
        active_policy = policy or self._eviction_policy
        if active_policy is None:
            raise ValueError("no eviction policy configured; pass one or set it in the constructor")

        result = active_policy.evict(
            self._store, scope_id=scope_id, memory_types=memory_types
        )
        for evicted_id in result.evicted_ids:
            self._vector_index.delete(evicted_id)
        return result

    # -- Lifecycle --

    def close(self) -> None:
        self._cache.close()
        self._cache_vector_index.close()
        self._vector_index.close()
        self._manager.close()

    def __enter__(self) -> MemLiteEngine:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _index(self, item: MemoryItem) -> None:
        vector = self._embedding_provider.embed([item.content])[0]
        self._vector_index.upsert(
            memory_id=item.id,
            scope_id=item.scope_id,
            memory_type=item.memory_type,
            model_id=self._embedding_provider.model_id,
            vector=vector,
        )
