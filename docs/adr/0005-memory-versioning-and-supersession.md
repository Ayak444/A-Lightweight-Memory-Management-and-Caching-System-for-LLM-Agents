# ADR-0005: Memory Versioning and Supersession

## Context

In long-running agent tasks, facts change: a deployment region moves, a library version is updated, a user preference is revised. The memory system must handle these updates without silently serving stale information or losing audit history.

## Decision

Memory updates use a **supersession** model rather than in-place mutation:

1. The old memory's status is set to `superseded` (not deleted).
2. A new memory is created with the updated content.
3. A `supersedes` relation is recorded in the `memory_relations` table.
4. The old memory's version counter is incremented for optimistic concurrency tracking.
5. The old memory's vector embedding is deleted; the new memory gets a fresh embedding.

Retrieval filters exclude `superseded` and `deleted` entries. The full history remains queryable for audit, diff, and debugging.

## Consequences

- **Positive**: Complete audit trail; any past state can be reconstructed.
- **Positive**: Vector index only contains active entries, avoiding stale similarity matches.
- **Positive**: `supersedes` relations enable traversal of update chains.
- **Negative**: Storage grows monotonically (soft-deletes only). A periodic compaction could be added later.
- **Negative**: `content_hash` deduplication only applies within the same scope/type/status, so a superseded entry with the same content as a new one does not prevent re-creation.
