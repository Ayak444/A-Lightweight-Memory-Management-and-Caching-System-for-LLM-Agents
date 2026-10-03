"""Provider protocols for LLM completion and token counting.

Core logic must not import any specific LLM SDK.  These minimal protocols
allow tests to use a deterministic fake and production to swap in OpenAI
or any other provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class CompletionRequest:
    """A provider-agnostic LLM completion request."""

    messages: list[dict[str, str]]
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 1024
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompletionResult:
    """A provider-agnostic LLM completion result."""

    content: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.total_tokens:
            self.total_tokens = self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "metadata": self.metadata,
        }


class LLMProvider(Protocol):
    """Minimal protocol for LLM completion."""

    def complete(self, request: CompletionRequest) -> CompletionResult: ...


class TokenCounter(Protocol):
    """Minimal protocol for token counting."""

    def count(self, text: str, model: str | None = None) -> int: ...
