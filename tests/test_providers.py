"""Tests for provider protocols and fakes."""

from __future__ import annotations

import unittest

from memlite.providers import CompletionRequest, CompletionResult
from memlite.providers.fake import FakeLLMProvider, FakeTokenCounter


class FakeLLMProviderTestCase(unittest.TestCase):
    def test_produces_deterministic_response(self) -> None:
        provider = FakeLLMProvider()
        request = CompletionRequest(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is 2+2?"},
            ]
        )
        result = provider.complete(request)
        self.assertIn("What is 2+2?", result.content)
        self.assertGreater(result.input_tokens, 0)
        self.assertGreater(result.output_tokens, 0)
        self.assertEqual(result.total_tokens, result.input_tokens + result.output_tokens)

    def test_same_input_gives_same_output(self) -> None:
        provider = FakeLLMProvider()
        request = CompletionRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        r1 = provider.complete(request)
        r2 = provider.complete(request)
        self.assertEqual(r1.content, r2.content)


class FakeTokenCounterTestCase(unittest.TestCase):
    def test_count_returns_positive_integer(self) -> None:
        counter = FakeTokenCounter()
        self.assertGreater(counter.count("Hello, world!"), 0)

    def test_longer_text_produces_more_tokens(self) -> None:
        counter = FakeTokenCounter()
        short = counter.count("hi")
        long = counter.count("This is a significantly longer piece of text for counting.")
        self.assertGreater(long, short)

    def test_empty_string_returns_at_least_one(self) -> None:
        counter = FakeTokenCounter()
        self.assertGreaterEqual(counter.count(""), 1)


class CompletionResultTestCase(unittest.TestCase):
    def test_total_tokens_auto_computed(self) -> None:
        result = CompletionResult(content="x", input_tokens=10, output_tokens=5)
        self.assertEqual(result.total_tokens, 15)

    def test_to_dict(self) -> None:
        result = CompletionResult(content="x", model="test", input_tokens=1, output_tokens=2)
        d = result.to_dict()
        self.assertEqual(d["content"], "x")
        self.assertEqual(d["total_tokens"], 3)


if __name__ == "__main__":
    unittest.main()
