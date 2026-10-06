"""Offline integration experiment; fake-provider tokens are estimates, not API usage."""

from __future__ import annotations

import json
import statistics
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from memlite.agent.loop import AgentLoop
from memlite.engine import MemLiteEngine
from memlite.providers import CompletionRequest, CompletionResult
from memlite.providers.fake import FakeLLMProvider

QUERIES = (
    "Database storage SQLite",
    "Deployment region Singapore",
    "License packages MIT Apache",
    "Programming language Python",
    "User interface React",
    "Test framework unittest",
)


class CountingProvider(FakeLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        return super().complete(request)


def run_agent_cache_benchmark(
    output_directory: str | Path,
    *,
    repeats: int = 5,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    results: list[dict[str, Any]] = []
    expected_outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="memlite-agent-benchmark-") as temporary:
        for enabled in (False, True):
            provider = CountingProvider()
            outputs: list[str] = []
            tokens = 0
            timings: list[float] = []
            with MemLiteEngine(Path(temporary) / f"cache-{enabled}.db") as engine:
                agent = AgentLoop(engine, provider)
                for _ in range(repeats):
                    for index, query in enumerate(QUERIES):
                        started = perf_counter()
                        response = agent.run(
                            query,
                            scope_id=f"topic-{index}",
                            model_id="fake-llm-v1",
                            use_cache=enabled,
                        )
                        timings.append((perf_counter() - started) * 1000)
                        outputs.append(response.content)
                        tokens += response.total_tokens
                stats = engine.cache_stats()
            if not enabled:
                expected_outputs = outputs
            results.append(
                {
                    "cache_enabled": enabled,
                    "tasks": len(outputs),
                    "provider_calls": provider.calls,
                    "cache_hits": stats.hits,
                    "cache_hit_rate": stats.hit_rate,
                    "estimated_provider_tokens": tokens,
                    "output_identity_rate": sum(
                        actual == expected
                        for actual, expected in zip(outputs, expected_outputs, strict=True)
                    )
                    / len(outputs),
                    "latency_ms_p50": statistics.median(timings),
                    "latency_ms_p95": sorted(timings)[
                        min(len(timings) - 1, int(len(timings) * 0.95))
                    ],
                }
            )
    report = {
        "provider": "FakeLLMProvider",
        "repeats": repeats,
        "unique_queries": len(QUERIES),
        "results": results,
        "avoided_provider_calls": results[0]["provider_calls"] - results[1]["provider_calls"],
        "notes": [
            "Each topic uses its own scope and repeats an identical query in unchanged context.",
            "This measures exact-cache integration, not paraphrase quality or answer correctness.",
            "Token counts use the fake provider's UTF-8 byte estimate; no paid API calls occur.",
            "Local timing includes SQLite overhead; fake calls have no network delay.",
        ],
    }
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "agent_cache_comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
