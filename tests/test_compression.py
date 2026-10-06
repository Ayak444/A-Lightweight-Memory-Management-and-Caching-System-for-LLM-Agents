from __future__ import annotations

import unittest

from memlite.policies.compression import abstractive_compress, extractive_compress
from memlite.providers import CompletionRequest, CompletionResult


class SummaryProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        return CompletionResult(content=self.response)


class CompressionTests(unittest.TestCase):
    def test_oversized_first_sentence_does_not_break_budget(self) -> None:
        result = extractive_compress(
            "Database " + "x" * 200 + ". SQLite.", "Database", token_budget=4
        )
        self.assertEqual(result.compressed_text, "SQLite.")
        self.assertLessEqual(result.compressed_tokens, 4)

    def test_joined_text_and_empty_result_respect_budget(self) -> None:
        result = extractive_compress("ABC. DEF.", "", token_budget=2)
        self.assertLessEqual(result.compressed_tokens, 2)
        empty = extractive_compress("x" * 100, "x", token_budget=1)
        self.assertEqual(empty.compressed_text, "")
        self.assertEqual(empty.compressed_tokens, 0)

    def test_relevance_selection_preserves_sentence_order(self) -> None:
        result = extractive_compress(
            "Cloud costs. SQLite database. Random news.",
            "SQLite database.",
            token_budget=10,
            min_score=0.5,
        )
        self.assertEqual(result.compressed_text, "SQLite database.")

    def test_summary_shortcut_and_generation(self) -> None:
        provider = SummaryProvider("SQLite")
        short = abstractive_compress("DB", provider, token_budget=5)
        self.assertEqual(short.compressed_text, "DB")
        self.assertEqual(provider.requests, [])
        result = abstractive_compress("SQLite project database. " * 20, provider, token_budget=5)
        self.assertEqual(result.compressed_text, "SQLite")
        self.assertEqual(provider.requests[0].max_tokens, 5)

    def test_invalid_budget_and_provider_overflow_fail_explicitly(self) -> None:
        for compress in (
            lambda: extractive_compress("abc", "", token_budget=0),
            lambda: abstractive_compress("abc", SummaryProvider("x"), token_budget=0),
            lambda: abstractive_compress("x" * 100, SummaryProvider("x" * 100), token_budget=2),
        ):
            with self.assertRaises(ValueError):
                compress()
