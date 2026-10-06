"""Public package interface for MemLite-Agent."""

from memlite.cache import (
    CacheEntry,
    CacheEventType,
    CacheLookupResult,
    CacheStats,
    CacheStatus,
    ScopeContext,
    SemanticCache,
)
from memlite.manager import MemoryManager
from memlite.models import MemoryItem, MemoryStatus, MemoryType, SourceType
from memlite.policies.eviction import (
    EvictionResult,
    HybridEviction,
    ImportanceProtectedEviction,
    LFUEviction,
    LRUEviction,
    TTLEviction,
)
from memlite.storage.sqlite import SQLiteMemoryStore

__all__ = [
    "CacheEntry",
    "CacheEventType",
    "CacheLookupResult",
    "CacheStats",
    "CacheStatus",
    "EvictionResult",
    "HybridEviction",
    "ImportanceProtectedEviction",
    "LFUEviction",
    "LRUEviction",
    "MemoryItem",
    "MemoryManager",
    "MemoryStatus",
    "MemoryType",
    "SQLiteMemoryStore",
    "ScopeContext",
    "SemanticCache",
    "SourceType",
    "TTLEviction",
]
