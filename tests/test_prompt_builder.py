import unittest

from memlite.agent.prompt_builder import PromptBuilder
from memlite.models import MemoryItem, MemoryType, SourceType, utc_now
from memlite.policies.retrieval import RetrievalCandidate, RetrievalResponse, ScoreBreakdown
from memlite.providers.fake import FakeLLMProvider


class TestPromptBuilder(unittest.TestCase):
    def setUp(self):
        self.item1 = MemoryItem(
            id="1",
            memory_type=MemoryType.SEMANTIC,
            scope_id="user1",
            content=(
                "This is a very long sentence that has some facts about apples. Apples are red."
            ),
            source_type=SourceType.USER,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        score = ScoreBreakdown(0.9, 0.9, 0.5, 1.0, 1.0, 0.0, 0.9)
        self.res1 = RetrievalCandidate(self.item1, score, estimated_tokens=20, selected=True)
        self.retrieval_response = RetrievalResponse(
            query="apples",
            scope_id="user1",
            candidates=[self.res1],
            selected_memory_ids=["1"],
            selected_tokens=20,
        )
        self.provider = FakeLLMProvider()
        self.provider.requests = []

        def fake_complete(request):
            self.provider.requests.append(request)
            from memlite.providers import CompletionResult

            return CompletionResult(content="- Apples are red.", model="fake")

        self.provider.complete = fake_complete

    def test_default_is_extractive(self):
        builder = PromptBuilder(memory_token_budget=5)
        messages = builder.build_messages("apples", self.retrieval_response)
        system_msg = next(
            (
                m
                for m in messages
                if m["role"] == "system" and "Here is some relevant context" in m["content"]
            ),
            None,
        )
        self.assertIsNotNone(system_msg)
        # extractive keeps sentences
        self.assertIn("Apples are red.", system_msg["content"])

    def test_abstractive_compression(self):
        builder = PromptBuilder(
            memory_token_budget=10, compression_strategy="abstractive", llm_provider=self.provider
        )
        messages = builder.build_messages("apples", self.retrieval_response)
        system_msg = next(
            (
                m
                for m in messages
                if m["role"] == "system" and "Here is some relevant context" in m["content"]
            ),
            None,
        )
        self.assertIsNotNone(system_msg)
        self.assertEqual(len(self.provider.requests), 1)
        self.assertIn("- Apples are red.", system_msg["content"])

    def test_none_compression(self):
        builder = PromptBuilder(memory_token_budget=5, compression_strategy="none")
        messages = builder.build_messages("apples", self.retrieval_response)
        system_msg = next(
            (
                m
                for m in messages
                if m["role"] == "system" and "Here is some relevant context" in m["content"]
            ),
            None,
        )
        self.assertIsNotNone(system_msg)
        # Should contain the full original text since no compression
        self.assertIn(
            "This is a very long sentence that has some facts about apples. Apples are red.",
            system_msg["content"],
        )
