# ADR-0004: Cache Scope and Invalidation

## Context

Semantic cache can return stale or incorrect answers when the execution context changes — for example, after switching LLM models, updating the system prompt, or modifying available tools.

## Decision

Each cache entry is keyed not only by the normalized query text but also by a **scope fingerprint** computed from:

```python
cache_scope = hash(
    normalized_query,
    system_prompt_version,
    model_id,
    tool_schema_version,
    relevant_context_fingerprint,
)
```

A cache hit is **rejected** when the candidate entry's scope fingerprint does not match the current request context. The rejection is logged as a `rejected_hit` event for observability.

Cache entries support:
- **TTL-based expiration**: entries expire after a configurable duration.
- **Manual invalidation**: individual entries or entire scopes can be invalidated.
- **Hit/miss/rejected-hit event log**: every lookup is recorded for analysis.

## Consequences

- **Positive**: Prevents cross-context cache poisoning (e.g., GPT-4 answer served to a GPT-3.5 request).
- **Positive**: Rejected hits are visible in the event log, making debugging straightforward.
- **Negative**: Changing any context dimension (model, prompt, tools) effectively invalidates all cache entries for that scope.
- **Mitigation**: Scope fingerprint granularity is configurable; fields can be left empty to broaden cache sharing.
