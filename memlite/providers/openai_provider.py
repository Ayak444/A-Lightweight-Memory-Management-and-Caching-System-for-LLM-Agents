from __future__ import annotations

import logging

import openai
import tiktoken

from memlite.providers import CompletionRequest, CompletionResult, LLMProvider, TokenCounter

logger = logging.getLogger(__name__)


class OpenAILLMProvider(LLMProvider):
    """OpenAI implementation of the LLMProvider protocol."""

    def __init__(
        self, client: openai.Client | None = None, default_model: str = "gpt-4o-mini"
    ) -> None:
        self.client = client or openai.Client()
        self.default_model = default_model

    def complete(self, request: CompletionRequest) -> CompletionResult:
        model = request.model or self.default_model

        # Convert request to openai format
        messages = request.messages

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        choice = response.choices[0]
        content = choice.message.content or ""

        input_tokens = 0
        output_tokens = 0
        if response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

        return CompletionResult(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata={"finish_reason": choice.finish_reason},
        )


class OpenAITokenCounter(TokenCounter):
    """TokenCounter implementation using tiktoken for OpenAI models."""

    def __init__(self, default_model: str = "gpt-4o-mini") -> None:
        self.default_model = default_model

    def count(self, text: str, model: str | None = None) -> int:
        model_name = model or self.default_model
        try:
            encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            # Fallback to cl100k_base for unknown models
            logger.warning(
                "Unknown model %s for token counting, falling back to cl100k_base", model_name
            )
            encoding = tiktoken.get_encoding("cl100k_base")

        return len(encoding.encode(text))
