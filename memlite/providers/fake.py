"""Deterministic fake providers for offline testing and benchmarks.

These never call any remote API and produce repeatable results.
"""

from __future__ import annotations

import hashlib
import math

from memlite.providers import CompletionRequest, CompletionResult


class FakeLLMProvider:
    """Returns a canned response derived from the last user message.

    Good enough for integration tests and offline benchmarks where the
    actual LLM response content is not being evaluated.
    """

    def __init__(self, model_id: str = "fake-llm-v1") -> None:
        self._model_id = model_id

    def complete(self, request: CompletionRequest) -> CompletionResult:
        last_user_message = ""
        for message in reversed(request.messages):
            if message.get("role") == "user":
                last_user_message = message.get("content", "")
                break

        response_content = f"[fake-response] Acknowledged: {last_user_message[:80]}"
        input_tokens = sum(
            _estimate_tokens(msg.get("content", "")) for msg in request.messages
        )
        output_tokens = _estimate_tokens(response_content)

        return CompletionResult(
            content=response_content,
            model=self._model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


class FakeTokenCounter:
    """Approximates token count as ceil(bytes / 4).

    Matches the estimate used in ``retrieval.estimate_tokens`` so that
    offline benchmarks produce consistent numbers.
    """

    def count(self, text: str, model: str | None = None) -> int:
        return _estimate_tokens(text)


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))
