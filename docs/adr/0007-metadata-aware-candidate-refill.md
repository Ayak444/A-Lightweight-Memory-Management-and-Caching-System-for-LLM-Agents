# ADR 0007: Metadata-Aware Candidate Refill

## Status

Accepted, 2026-10-04.

## Context

Vector search returns a ranked prefix before metadata checks. Expired, missing,
deleted, superseded, duplicate, wrong-scope, or wrong-type records can consume
that prefix. Filtering them without refilling may hide a valid memory behind it.
The fixed challenge dataset reproduces this with 25 expired records and a valid
fact outside the initial top-20.

## Decision

- Count `candidate_limit` as unique, finite, metadata-authorized candidates.
- Grow the vector prefix geometrically until this pool is full, the backend is
  exhausted, or `candidate_scan_limit` is reached. The explicit cap must be an
  integer at least as large as `candidate_limit`. `None` resolves to
  `max(100000, candidate_limit)` for compatibility with larger existing pools.
- Preserve the vector search signature. For an unchanged index, increasing
  `limit` must retain its previous similarity-ranked prefix and deterministic
  tie order. This is supported by the current SQLite exact-search adapter;
  future ANN adapters must honor or explicitly redesign this contract.
- Apply hybrid scoring, minimum similarity, result count, and token budget after
  the usable pool is built. Those selection rejections do not trigger refill.
- Freeze eligibility/scoring time once per request and touch selected records
  only once. Do not delete records, repair indexes, or perform TTL eviction as a
  side effect of retrieval. Refill is not an atomic cross-database snapshot.
- Add trace fields `search_rounds`, `scanned_hits`, `search_limit`, and
  `scan_limit_reached`. `scanned_hits` means the final returned prefix length,
  not cumulative hits or SQLite rows examined. The cap flag conservatively
  indicates an underfilled pool at the cap, not proof of a matching unseen fact.

## Consequences

TTL cleanup is no longer a prerequisite for finding valid facts behind expired
vector rows within the scan cap. It remains useful for index/storage maintenance.
Both metadata and derived index contents remain intact on a read.

SQLite rescans and sorts its full matching vector corpus on each round. The cap
bounds the returned prefix and refill metadata work, not the adapter's internal
row scan, remote cost, or wall-clock latency. Large stale prefixes can therefore
be expensive or still produce a partial result at the cap. Schedule separate
index maintenance rather than increasing the cap without measuring the cost.

Replenishing past invalid metadata cannot fix active but false memories, protect
important records from capacity eviction, or improve semantic understanding.

## Validation

See `tests/test_retrieval_refill.py` and `tests/test_refill_comparison.py`, the
fixed `experiments/datasets/challenge.json`, and
`docs/RETRIEVAL_REFILL_20261004.zh-TW.md`. The paired comparison uses identical
fixtures and parameters except `candidate_scan_limit`, repeats three times, and
checks its no-refill condition against the saved original query traces.
