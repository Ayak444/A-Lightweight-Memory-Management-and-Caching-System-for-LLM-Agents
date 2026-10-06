"""Generate a human-readable summary.md from benchmark results."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def generate_summary(results_dir: str | Path) -> str:
    """Read benchmark JSON outputs and produce a Markdown summary."""
    results_dir = Path(results_dir)
    sections: list[str] = []

    sections.append("# Benchmark Summary Report")
    sections.append("")
    sections.append(f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    sections.append("")

    # -- Environment --
    env_path = results_dir / "environment.json"
    if env_path.exists():
        env = json.loads(env_path.read_text(encoding="utf-8"))
        sections.append("## Environment")
        sections.append("")
        sections.append(f"- **Git commit**: `{env.get('git_commit', 'N/A')}`")
        sections.append(f"- **Branch**: `{env.get('git_branch', 'N/A')}`")
        sections.append(f"- **Python**: `{env.get('python_version', 'N/A')}`")
        sections.append(f"- **Platform**: `{env.get('platform', 'N/A')}`")
        pkgs = env.get("packages", {})
        if pkgs:
            sections.append("- **Packages**:")
            for pkg, ver in pkgs.items():
                sections.append(f"  - {pkg}: `{ver or 'N/A'}`")
        sections.append("")

    # -- Comparison results --
    comparison_path = results_dir / "comparison.json"
    if comparison_path.exists():
        data = json.loads(comparison_path.read_text(encoding="utf-8"))
        sections.append("## Dataset Info")
        sections.append("")
        sections.append(f"- Version: `{data.get('dataset_version', 'N/A')}`")
        sections.append(f"- Sequences: {data.get('dataset_sequences', 'N/A')}")
        sections.append("")

        # Strategy comparison table
        strategies = data.get("strategy_comparison", [])
        if strategies:
            sections.append("## Strategy Comparison")
            sections.append("")
            sections.append(
                "| Strategy | Queries | Pass Rate | Precision | Recall | MRR "
                "| Tokens | P50 ms | P95 ms |"
            )
            sections.append(
                "|----------|---------|-----------|-----------|--------|-----"
                "|--------|--------|--------|"
            )
            for s in strategies:
                sections.append(
                    f"| {s['strategy']} "
                    f"| {s['queries']} "
                    f"| {s['pass_rate']:.2%} "
                    f"| {s['mean_precision']:.3f} "
                    f"| {s['mean_recall']:.3f} "
                    f"| {s['mean_reciprocal_rank']:.3f} "
                    f"| {s['mean_selected_tokens']:.0f} "
                    f"| {s['latency_ms_p50']:.1f} "
                    f"| {s['latency_ms_p95']:.1f} |"
                )
            sections.append("")

        # Token budget comparison table
        budgets = data.get("token_budget_comparison", [])
        if budgets:
            sections.append("## Token Budget Comparison")
            sections.append("")
            sections.append("| Budget | Pass Rate | Precision | Recall | MRR | Tokens |")
            sections.append("|--------|-----------|-----------|--------|-----|--------|")
            for b in budgets:
                sections.append(
                    f"| {b.get('token_budget', b['strategy'])} "
                    f"| {b['pass_rate']:.2%} "
                    f"| {b['mean_precision']:.3f} "
                    f"| {b['mean_recall']:.3f} "
                    f"| {b['mean_reciprocal_rank']:.3f} "
                    f"| {b['mean_selected_tokens']:.0f} |"
                )
            sections.append("")

        # Corpus latency table
        latencies = data.get("corpus_latency_comparison", [])
        if latencies:
            sections.append("## Corpus Size vs Latency")
            sections.append("")
            sections.append("| Corpus Size | Runs | P50 ms | P95 ms |")
            sections.append("|-------------|------|--------|--------|")
            for latency in latencies:
                sections.append(
                    f"| {latency['corpus_size']:,} "
                    f"| {latency['runs']} "
                    f"| {latency['latency_ms_p50']:.2f} "
                    f"| {latency['latency_ms_p95']:.2f} |"
                )
            sections.append("")

        # Notes
        notes = data.get("notes", [])
        if notes:
            sections.append("## Notes")
            sections.append("")
            for note in notes:
                sections.append(f"- {note}")
            sections.append("")

    agent_path = results_dir / "agent_cache_comparison.json"
    if agent_path.exists():
        agent_data = json.loads(agent_path.read_text(encoding="utf-8"))
        sections.extend(
            [
                "## Offline Agent Cache Comparison",
                "",
                "| Cache | Tasks | Calls | Hit Rate | Est. Tokens | Output Identity | P50 ms |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for result in agent_data["results"]:
            sections.append(
                f"| {result['cache_enabled']} | {result['tasks']} "
                f"| {result['provider_calls']} | {result['cache_hit_rate']:.2%} "
                f"| {result['estimated_provider_tokens']} "
                f"| {result['output_identity_rate']:.2%} | {result['latency_ms_p50']:.3f} |"
            )
        sections.extend(["", *[f"- {note}" for note in agent_data["notes"]], ""])

    # -- Limitations --
    sections.append("## Known Limitations & Failure Cases")
    sections.append("")
    sections.append(
        "1. **Lexical embedding baseline**: The deterministic hash embedding uses "
        "token overlap rather than true semantic similarity. This means synonyms and "
        "paraphrases receive lower similarity than they would with a real embedding model."
    )
    sections.append(
        "2. **Single-turn queries**: The benchmark tests single retrieval queries, "
        "not multi-turn agent conversations. Real-world performance may differ."
    )
    sections.append(
        "3. **No LLM evaluation**: Task success rate requires an LLM judge or "
        "deterministic checker, which is not yet integrated."
    )
    sections.append(
        "4. **Pollution penalty is static**: The `pollution_penalty` metadata field "
        "is set manually in test data; a production system would need automatic "
        "detection of contradictions."
    )
    sections.append("")

    return "\n".join(sections)


def save_summary(results_dir: str | Path) -> Path:
    """Generate and write summary.md to the results directory."""
    results_dir = Path(results_dir)
    content = generate_summary(results_dir)
    output_path = results_dir / "summary.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path
