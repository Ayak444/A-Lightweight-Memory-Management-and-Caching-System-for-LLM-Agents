# ADR 0008: Bounded Importance Protection

## Status

Accepted for opt-in experiments, 2026-10-04. Not the default eviction policy.

## Context

LRU and LFU can evict a cold but important fact while retaining recent or popular
noise. Importance is already stored independently of access history, but it is a
caller rating, not verified truth. Unbounded pinning would defeat capacity limits
and could preserve false memories indefinitely.

## Decision

Add `ImportanceProtectedEviction` around an existing LRU or LFU capacity policy.
The declared experiment reserves one slot for active, unexpired memories with
importance >= 0.8 and confidence >= 0.8. The quota is inside total capacity, not
additional capacity. The constructor permits zero slots to disable protection;
other quotas must be integers between zero and capacity.

When more records qualify than the quota, choose by importance descending,
confidence descending, then memory ID ascending. This is reproducible but not a
semantic tie-break. Evict unreserved records using the original LRU/LFU order.
Keep the original policies' tie behavior unchanged.

Protection never overrides source scope/type filtering or expiry. It may be
combined with `HybridEviction` so TTL cleanup runs first. `protected_ids` in
`EvictionResult` records reserved IDs, even when no deletion was necessary;
reservation is not evidence that a record was saved from eviction.

The new policy refuses a source snapshot beyond 100000 records before performing
its own deletions, rather than acting on a truncated list and reporting a false
capacity guarantee. Capacity is measured over eligible active records only.
Concurrent writers are not serialized by this policy; it does not provide an
atomic scope snapshot or cross-database transaction. The engine retains existing
soft deletion, vector cleanup, and affected-scope cache invalidation behavior.

## Evaluation Contract

Keep `challenge-1.1.0` and its original 12 cases unchanged. Add a separate versioned
`protection-1.0.0` dataset with important-but-false, low-confidence, protected-pool
overflow, ordinary rare, and expired-important cases in both vocabulary splits.
Freeze rules before the evaluation run; never pass expected/forbidden labels to
the policy or tune ratings after inspecting results.

Compare LRU/LFU with and without protection at capacities 2, 4 and 8, plus a
no-eviction retrieval baseline. Run three independent database reconstructions
per case/strategy. Record retention, retrieval pass/precision/recall, pollution,
protected false records, capacity violations, traces, hashes, and environment.
Check unchanged controls against previous saved traces when available.

## Consequences

High importance and confidence can help retain known important facts but can
equally amplify incorrect ratings. They are not a provenance, authorization,
calibration, or truth-verification mechanism. Do not enable protection by default
or infer user intent to pin records from their retrieval popularity.

Report benefit and harm together. Synthetic retrieval pass is not LLM task
success, and repeated cases do not become additional independent samples.
Conflict resolution and trustworthy evidence-backed rating remain separate work.
