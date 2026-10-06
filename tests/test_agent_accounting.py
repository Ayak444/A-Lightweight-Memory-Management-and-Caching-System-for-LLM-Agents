from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memlite.agent.loop import AgentLoop
from memlite.agent.prompt_builder import PromptBuilder
from memlite.engine import MemLiteEngine
from memlite.models import MemoryType, SourceType
from memlite.policies.retrieval import RetrievalConfig
from memlite.providers import CompletionRequest, CompletionResult


class UsageRecorder:
    def __init__(self, summary_text: str = "SQLite.") -> None:
        self.summary_text = summary_text
        self.requests: list[CompletionRequest] = []
        self.results: list[CompletionResult] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        summary = len(request.messages) == 1
        result = CompletionResult(
            content=self.summary_text if summary else "We decided SQLite is the database.",
            model=request.model,
            input_tokens=20 if summary else 7,
            output_tokens=2 if summary else 3,
        )
        self.results.append(result)
        return result


class AgentAccountingTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.engine = MemLiteEngine(
            Path(temporary.name) / "memory.db",
            retrieval_config=RetrievalConfig(min_similarity=0.0, token_budget=5000),
        )
        self.addCleanup(self.engine.close)
        self.provider = UsageRecorder()

    def summary_agent(self, **kwargs: str) -> AgentLoop:
        self.engine.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="summary",
            content="SQLite database configuration. " + "background information. " * 20,
        )
        builder = PromptBuilder(memory_token_budget=8, compression_strategy="abstractive", **kwargs)
        return AgentLoop(self.engine, self.provider, builder)

    def test_cache_hit_performs_authorized_extraction_without_provider_call(self) -> None:
        agent = AgentLoop(self.engine, self.provider)
        agent.run("Which database?", "warm")
        result = agent.run("Which database?", "warm", auto_extract=True)
        self.assertTrue(result.metadata["cache_hit"])
        self.assertEqual(len(self.provider.requests), 1)
        memories = self.engine.list_memories(scope_id="warm")
        self.assertEqual(len(memories), 1)
        self.assertIs(memories[0].source_type, SourceType.LLM)
        self.assertEqual(memories[0].confidence, 0.7)
        self.assertEqual(memories[0].source_ref, "Which database?")
        self.assertEqual(self.engine.list_memories(scope_id="other"), [])
        self.assertEqual(self.engine.cache_stats().active_entries, 0)

    def test_l3_cache_hit_makes_no_summary_or_completion_call(self) -> None:
        agent = self.summary_agent()
        first = agent.run("SQLite database", "summary", model_id="main-model")
        second = agent.run("SQLite database", "summary", model_id="main-model")
        self.assertEqual(len(self.provider.requests), 2)
        self.assertEqual(first.content, second.content)
        self.assertTrue(second.metadata["cache_hit"])
        self.assertEqual(second.total_tokens, 0)
        self.assertEqual(second.metadata["provider_calls"], [])

    def test_usage_is_aggregated_and_models_remain_separate(self) -> None:
        agent = self.summary_agent(summary_model="summary-model")
        result = agent.run("SQLite database", "summary", model_id="main-model")
        self.assertEqual(
            (result.input_tokens, result.output_tokens, result.total_tokens), (27, 5, 32)
        )
        calls = result.metadata["provider_calls"]
        self.assertEqual([row["stage"] for row in calls], ["summary", "completion"])
        self.assertEqual([row["model"] for row in calls], ["summary-model", "main-model"])
        self.assertEqual(sum(row["total_tokens"] for row in calls), result.total_tokens)
        self.assertTrue(all(row["latency_ms"] >= 0 for row in calls))
        self.assertEqual(self.provider.results[-1].total_tokens, 10)

    def test_l3_cache_identity_changes_with_model_budget_and_raw_context(self) -> None:
        agent = self.summary_agent()
        agent.run("SQLite database", "summary", model_id="main-model")
        agent.prompt_builder.summary_model = "another-summary-model"
        agent.run("SQLite database", "summary", model_id="main-model")
        agent.prompt_builder.memory_token_budget = 9
        agent.run("SQLite database", "summary", model_id="main-model")
        self.assertEqual(len(self.provider.requests), 6)
        self.engine.remember(
            memory_type=MemoryType.SEMANTIC, scope_id="summary", content="SQLite updated context."
        )
        agent.run("SQLite database", "summary", model_id="main-model")
        self.assertEqual(len(self.provider.requests), 8)

    def test_short_context_has_no_summary_usage(self) -> None:
        self.engine.remember(
            memory_type=MemoryType.SEMANTIC, scope_id="short", content="DB SQLite."
        )
        agent = AgentLoop(
            self.engine,
            self.provider,
            PromptBuilder(memory_token_budget=100, compression_strategy="abstractive"),
        )
        result = agent.run("DB SQLite", "short", model_id="main-model")
        self.assertEqual(len(self.provider.requests), 1)
        self.assertEqual(result.total_tokens, 10)
        self.assertEqual(
            [row["stage"] for row in result.metadata["provider_calls"]], ["completion"]
        )

    def test_failed_summary_does_not_call_completion_or_cache_bad_output(self) -> None:
        agent = self.summary_agent()
        self.provider.summary_text = "x" * 100
        with self.assertRaisesRegex(ValueError, "exceeds"):
            agent.run("SQLite database", "summary")
        self.assertEqual(len(self.provider.requests), 1)
        self.assertEqual(self.engine.cache_stats().total_entries, 0)

    def test_standalone_missing_provider_and_invalid_strategy_fail_explicitly(self) -> None:
        self.summary_agent()
        response = self.engine.retrieve("SQLite database", scope_id="summary")
        with self.assertRaisesRegex(ValueError, "llm_provider"):
            PromptBuilder(memory_token_budget=8, compression_strategy="abstractive").build_messages(
                "SQLite database", response
            )
        with self.assertRaises(ValueError):
            PromptBuilder(compression_strategy="misspelled")  # type: ignore[arg-type]

    def test_disabled_cache_still_accounts_for_every_l3_call(self) -> None:
        agent = self.summary_agent()
        for _ in range(2):
            result = agent.run("SQLite database", "summary", use_cache=False)
            self.assertEqual(result.total_tokens, 32)
        self.assertEqual(len(self.provider.requests), 4)
        self.assertEqual(self.engine.cache_stats().total_lookups, 0)
