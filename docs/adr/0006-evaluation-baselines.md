# ADR-0006: Evaluation Baselines

## Context

Demonstrating the value of hierarchical memory requires comparison against meaningful baselines. Without baselines, improved metrics could simply reflect task difficulty rather than system design.

## Decision

The evaluation framework defines the following experiment groups:

| Group | Description |
|-------|-------------|
| B0 | Full conversation history, no memory manager |
| B1 | Fixed recent window (last N tokens only) |
| E1 | Vector top-k memory, no compression or cache |
| E2 | Hierarchical memory with token budget |
| E3 | E2 + semantic cache |
| E4 | E3 + eviction and pollution handling |

All groups must use:
- Identical task sequences and inputs
- Same model, temperature, and system prompt version
- Same evaluation scorer and dataset version
- At least 3 repeated runs to account for provider variance

Results are recorded with full environment metadata (git commit, Python version, model, price snapshot) so that numbers remain interpretable months later.

## Consequences

- **Positive**: Each experiment group isolates one capability, enabling ablation-style analysis.
- **Positive**: B0/B1 baselines prevent over-claiming; if MemLite does not outperform B1 on some metrics, that finding is documented honestly.
- **Negative**: Running 6 groups × 3 repeats increases benchmark time. Offline fake providers mitigate cost.
- **Negative**: B0 (full history) may exceed context limits on longer sequences. This is itself a data point worth reporting.
