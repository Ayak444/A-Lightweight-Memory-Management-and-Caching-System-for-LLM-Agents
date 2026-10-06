from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from memlite.policies.compression import (
    CompressionResult,
    abstractive_compress,
    extractive_compress,
)
from memlite.policies.retrieval import RetrievalResponse
from memlite.providers import LLMProvider


@dataclass(frozen=True, slots=True)
class PromptBuildResult:
    messages: list[dict[str, str]]
    compression: CompressionResult | None = None


class PromptBuilder:
    """Builds prompts incorporating retrieved memories and task context."""

    def __init__(
        self,
        system_instruction: str = "You are a helpful AI assistant.",
        *,
        memory_token_budget: int | None = None,
        compression_strategy: Literal["none", "extractive", "abstractive"] = "extractive",
        llm_provider: LLMProvider | None = None,
        summary_model: str | None = None,
    ) -> None:
        if memory_token_budget is not None and (
            type(memory_token_budget) is not int or memory_token_budget < 1
        ):
            raise ValueError("memory_token_budget must be a positive integer or None")
        if compression_strategy not in ("none", "extractive", "abstractive"):
            raise ValueError("unsupported compression_strategy")
        if summary_model is not None and (
            not isinstance(summary_model, str) or not summary_model.strip()
        ):
            raise ValueError("summary_model must be a nonempty string or None")
        self.system_instruction = system_instruction
        self.memory_token_budget = memory_token_budget
        self.compression_strategy = compression_strategy
        self.llm_provider = llm_provider
        self.summary_model = summary_model

    def build_messages(
        self,
        task: str,
        retrieval_response: RetrievalResponse | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        *,
        apply_compression: bool = True,
        model_id: str = "",
    ) -> list[dict[str, str]]:
        """Build the messages array for the LLM.

        Args:
            task: The current user task/query.
            retrieval_response: The retrieved memories (if any).
            conversation_history: Optional recent conversation history.

        Returns:
            A list of message dictionaries (role, content).
        """
        return self.build_messages_with_trace(
            task,
            retrieval_response,
            conversation_history,
            apply_compression=apply_compression,
            model_id=model_id,
        ).messages

    def build_messages_with_trace(
        self,
        task: str,
        retrieval_response: RetrievalResponse | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        *,
        apply_compression: bool = True,
        model_id: str = "",
    ) -> PromptBuildResult:
        messages = [{"role": "system", "content": self.system_instruction}]
        compression: CompressionResult | None = None

        if retrieval_response and retrieval_response.candidates:
            memory_text = "\n".join(
                f"- {res.memory.content}" for res in retrieval_response.candidates if res.selected
            )
            if memory_text and self.memory_token_budget is not None and apply_compression:
                if self.compression_strategy == "extractive":
                    compression = extractive_compress(
                        memory_text, task, token_budget=self.memory_token_budget
                    )
                elif self.compression_strategy == "abstractive":
                    if self.llm_provider is None:
                        raise ValueError("abstractive compression requires an llm_provider")
                    compression = abstractive_compress(
                        memory_text,
                        self.llm_provider,
                        token_budget=self.memory_token_budget,
                        model=self.summary_model or model_id,
                    )
                if compression is not None:
                    memory_text = compression.compressed_text
            if memory_text:
                memory_prompt = (
                    "Here is some relevant context from previous interactions:\n"
                    f"{memory_text}\n\n"
                    "Please use this context to inform your answer if it is relevant."
                )
                messages.append({"role": "system", "content": memory_prompt})

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": task})
        return PromptBuildResult(messages, compression)
