# ADR-0003: Separate Metadata and Vector Index

## Context

MemLite-Agent needs both structured metadata (memory type, scope, TTL, version) and vector embeddings for similarity search. These have very different query patterns and consistency requirements.

## Decision

Keep metadata in SQLite as the single source of truth, and store embeddings in a separate vector-specific store (initially also SQLite, replaceable with Chroma/Qdrant later). The vector index is derived; if it diverges from metadata, an idempotent `reindex_scope` command rebuilds it.

## Consequences

- **Positive**: Metadata queries (filter by scope, type, status) use SQL efficiently. Vector search can be replaced without touching business logic.
- **Positive**: Partial failures (vector write fails, metadata succeeds) are recoverable via reindex.
- **Negative**: Write path must coordinate two stores. Forgetting to delete a vector entry after supersession leaks stale results.
- **Mitigation**: `MemLiteEngine` encapsulates dual-write; retrieval service post-validates every vector hit against metadata.
