from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memlite.agent.loop import AgentLoop
from memlite.agent.prompt_builder import PromptBuilder
from memlite.engine import MemLiteEngine
from memlite.models import MemoryType
from memlite.policies.retrieval import RetrievalConfig
from memlite.providers import CompletionRequest, CompletionResult


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        return CompletionResult(content="offline response")


class AgentCompressionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.engine = MemLiteEngine(
            Path(temporary.name) / "memory.db", retrieval_config=RetrievalConfig(token_budget=5000)
        )
        self.addCleanup(self.engine.close)
        self.memory = self.engine.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="project:a",
            content="Noise " + "x" * 200 + ". SQLite database.",
        )
        self.provider = RecordingProvider()

    def test_opt_in_compression_reaches_provider_without_modifying_source(self) -> None:
        agent = AgentLoop(self.engine, self.provider, PromptBuilder(memory_token_budget=5))
        agent.run("SQLite database.", "project:a", use_cache=False)
        context = self.provider.requests[0].messages[1]["content"]
        self.assertIn("SQLite database.", context)
        self.assertNotIn("x" * 200, context)
        self.assertEqual(
            self.engine.get_memory(self.memory.id, scope_id="project:a").content,
            self.memory.content,
        )

    def test_default_keeps_selected_context_unchanged(self) -> None:
        agent = AgentLoop(self.engine, self.provider)
        agent.run("SQLite database.", "project:a", use_cache=False)
        self.assertIn(self.memory.content, self.provider.requests[0].messages[1]["content"])

    def test_compression_budget_change_does_not_reuse_old_context_cache(self) -> None:
        builder = PromptBuilder(memory_token_budget=5)
        agent = AgentLoop(self.engine, self.provider, builder)
        agent.run("SQLite database.", "project:a")
        agent.run("SQLite database.", "project:a")
        self.assertEqual(len(self.provider.requests), 1)
        agent.prompt_builder = PromptBuilder(memory_token_budget=500)
        agent.run("SQLite database.", "project:a")
        self.assertEqual(len(self.provider.requests), 2)
        self.assertNotEqual(self.provider.requests[0].messages, self.provider.requests[1].messages)

    def test_empty_compression_never_invents_context(self) -> None:
        agent = AgentLoop(self.engine, self.provider, PromptBuilder(memory_token_budget=1))
        agent.run("SQLite database.", "project:a", use_cache=False)
        self.assertEqual(len(self.provider.requests[0].messages), 2)
        self.assertEqual(self.provider.requests[0].messages[-1]["content"], "SQLite database.")

    def test_rejected_and_cross_scope_memories_do_not_enter_compression(self) -> None:
        forbidden = "SQLite database. private secret for other scope."
        self.engine.remember(
            memory_type=MemoryType.SEMANTIC, scope_id="project:b", content=forbidden
        )
        response = self.engine.retrieve("SQLite database.", scope_id="project:a")
        response.candidates[0].selected = False
        builder = PromptBuilder(memory_token_budget=100)
        messages = builder.build_messages("SQLite database.", response)
        self.assertEqual(len(messages), 2)
        self.assertNotIn(forbidden, str(messages))

    def test_invalid_budget_is_rejected_at_construction(self) -> None:
        for budget in (0, -1, True, 1.5):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                PromptBuilder(memory_token_budget=budget)  # type: ignore[arg-type]
