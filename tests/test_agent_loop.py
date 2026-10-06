from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memlite.agent.loop import AgentLoop
from memlite.agent.prompt_builder import PromptBuilder
from memlite.engine import MemLiteEngine
from memlite.models import MemoryType
from memlite.providers import CompletionRequest, CompletionResult
from memlite.providers.fake import FakeLLMProvider


class RecordingProvider(FakeLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        return super().complete(request)


class AgentLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = MemLiteEngine(Path(self.directory.name) / "agent.db")
        self.addCleanup(self.engine.close)
        self.provider = RecordingProvider()
        self.agent = AgentLoop(self.engine, self.provider)

    def test_selected_memory_reaches_provider_and_repeated_query_avoids_call(self) -> None:
        self.engine.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="user",
            content="Project metadata database is SQLite",
        )
        first = self.agent.run("Project metadata database?", "user", model_id="model-a")
        second = self.agent.run("Project metadata database?", "user", model_id="model-a")
        self.assertEqual(len(self.provider.requests), 1)
        self.assertIn("SQLite", str(self.provider.requests[0].messages))
        self.assertEqual(first.content, second.content)
        self.assertTrue(second.metadata["cache_hit"])
        self.assertEqual(second.total_tokens, 0)
        self.assertEqual(second.model, "model-a")

    def test_model_prompt_version_tool_version_and_history_isolate_cache(self) -> None:
        query = "Which database?"
        self.agent.run(query, "user", model_id="model-a")
        self.agent.run(query, "user", model_id="model-b")
        self.agent.run(query, "user", model_id="model-b", system_prompt_version="v2")
        self.agent.run(
            query,
            "user",
            model_id="model-b",
            system_prompt_version="v2",
            tool_schema_version="tools-v2",
        )
        history = [{"role": "user", "content": "Discuss another project"}]
        self.agent.run(
            query,
            "user",
            model_id="model-b",
            system_prompt_version="v2",
            tool_schema_version="tools-v2",
            conversation_history=history,
        )
        self.assertEqual(len(self.provider.requests), 5)
        self.assertEqual(history, [{"role": "user", "content": "Discuss another project"}])

    def test_actual_instruction_and_scope_isolate_cache(self) -> None:
        self.agent.run("Which database?", "user")
        other = AgentLoop(self.engine, self.provider, PromptBuilder("Answer in French"))
        other.run("Which database?", "user")
        other.run("Which database?", "another-user")
        self.assertEqual(len(self.provider.requests), 3)

    def test_memory_mutation_invalidates_cached_answer(self) -> None:
        item = self.engine.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="user",
            content="Project database SQLite",
        )
        self.agent.run("Project database?", "user")
        self.engine.supersede(item.id, content="Project database PostgreSQL")
        self.assertEqual(self.engine.cache_stats().active_entries, 0)
        self.agent.run("Project database?", "user")
        self.assertEqual(len(self.provider.requests), 2)
        self.assertIn("PostgreSQL", str(self.provider.requests[-1].messages))
        self.assertNotIn("SQLite", str(self.provider.requests[-1].messages))

    def test_forget_and_new_memory_invalidate_only_affected_scope(self) -> None:
        item = self.engine.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="user",
            content="Project database SQLite",
        )
        self.agent.run("Project database?", "user")
        self.agent.run("Project database?", "other")
        self.engine.forget(item.id)
        self.assertEqual(self.engine.cache_stats().active_entries, 1)
        self.engine.remember(
            memory_type=MemoryType.SEMANTIC,
            scope_id="other",
            content="Project database MySQL",
        )
        self.assertEqual(self.engine.cache_stats().active_entries, 0)

    def test_remember_task_writes_memory_and_bypasses_response_cache(self) -> None:
        for _ in range(2):
            self.agent.run("Remember: project database SQLite", "user")
        self.assertEqual(len(self.provider.requests), 2)
        self.assertEqual(self.engine.cache_stats().total_entries, 0)
        response = self.engine.retrieve("project database SQLite", scope_id="user")
        self.assertEqual(len(response.selected_memory_ids), 1)

    def test_disabled_cache_makes_no_cache_events(self) -> None:
        for _ in range(2):
            self.agent.run("Which database?", "user", use_cache=False)
        self.assertEqual(len(self.provider.requests), 2)
        self.assertEqual(self.engine.cache_stats().total_lookups, 0)

    def test_provider_failure_does_not_cache_response(self) -> None:
        class BrokenProvider:
            def complete(self, request: CompletionRequest) -> CompletionResult:
                raise RuntimeError("provider failure")

        with self.assertRaisesRegex(RuntimeError, "provider failure"):
            AgentLoop(self.engine, BrokenProvider()).run("Which database?", "user")
        self.assertEqual(self.engine.cache_stats().total_entries, 0)

    def test_auto_extract_episodic_memory(self) -> None:
        def fake_complete(request):
            return CompletionResult(
                content="We have decided to use SQLite. Another preference is offline mode.",
                model="fake",
            )

        self.provider.complete = fake_complete
        self.agent.run("What database and mode?", "user", auto_extract=True)
        # Should extract two sentences because 'decided' and 'preference' are keywords
        memories = self.engine.list_memories(scope_id="user")
        self.assertEqual(len(memories), 2)
        for m in memories:
            self.assertEqual(m.memory_type, MemoryType.EPISODIC)
            self.assertEqual(m.importance, 0.5)
            self.assertEqual(m.confidence, 0.7)
            self.assertEqual(m.source_ref, "What database and mode?")
        contents = {m.content for m in memories}
        self.assertIn("We have decided to use SQLite.", contents)
        self.assertIn("Another preference is offline mode.", contents)
