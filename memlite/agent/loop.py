from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from hashlib import sha256
from time import perf_counter

from memlite.agent.prompt_builder import PromptBuilder
from memlite.cache import CacheEventType, ScopeContext
from memlite.engine import MemLiteEngine
from memlite.models import MemoryType, SourceType
from memlite.providers import CompletionRequest, CompletionResult, LLMProvider

logger = logging.getLogger(__name__)


class AgentLoop:
    """The main execution loop for the agent, coordinating memory, cache, and LLM."""

    def __init__(
        self,
        engine: MemLiteEngine,
        llm_provider: LLMProvider,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        self.engine = engine
        self.llm_provider = llm_provider
        self.prompt_builder = prompt_builder or PromptBuilder()
        if self.prompt_builder.llm_provider is None:
            self.prompt_builder.llm_provider = self.llm_provider

    def run(
        self,
        task: str,
        scope_id: str,
        system_prompt_version: str = "v1",
        model_id: str = "default-model",
        use_cache: bool = True,
        conversation_history: list[dict[str, str]] | None = None,
        tool_schema_version: str = "",
        auto_extract: bool = False,
    ) -> CompletionResult:
        """Execute a task, utilizing memory and cache.

        Args:
            task: The user query or task.
            scope_id: The scope/user ID.
            system_prompt_version: Used for cache invalidation when prompt changes.
            model_id: The LLM model to use.
            use_cache: Whether to try and use semantic cache.
            conversation_history: Recent conversation history (if any).
            tool_schema_version: Version for tool schema cache invalidation.
            auto_extract: Whether to auto-extract episodic memory from LLM responses.

        Returns:
            The LLM CompletionResult or cached result.
        """
        # 1. Retrieve relevant memory
        retrieval_response = self.engine.retrieve(
            task,
            scope_id=scope_id,
        )

        # 2. Build context
        deferred_summary = (
            self.prompt_builder.compression_strategy == "abstractive"
            and self.prompt_builder.memory_token_budget is not None
        )
        built = self.prompt_builder.build_messages_with_trace(
            task=task,
            retrieval_response=retrieval_response,
            conversation_history=conversation_history,
            apply_compression=not deferred_summary,
            model_id=model_id,
        )
        messages = built.messages

        # Exclude the current task so semantic rewrites can share unchanged context.
        context_identity: object = messages[:-1]
        if deferred_summary:
            # L3 cache identity must be available without making a summary call.
            context_identity = {
                "raw_messages": messages[:-1],
                "compression": "abstractive-v1",
                "budget": self.prompt_builder.memory_token_budget,
                "summary_model": self.prompt_builder.summary_model or model_id,
            }
        context_hash = sha256(
            json.dumps(context_identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        scope_context = ScopeContext(
            system_prompt_version=system_prompt_version,
            model_id=model_id,
            tool_schema_version=tool_schema_version,
            context_fingerprint=context_hash,
        )
        writes_memory = "remember" in task.lower() or "記住" in task
        cache_enabled = use_cache and not writes_memory
        if cache_enabled:
            cache_hit = self.engine.cache_lookup(
                task,
                scope_id=scope_id,
                scope_context=scope_context,
            )
            if cache_hit.event_type is CacheEventType.HIT and cache_hit.entry is not None:
                logger.info("Semantic cache hit for query: %s", task)
                self._extract_and_save_memory(
                    task, cache_hit.entry.response, scope_id, auto_extract=auto_extract
                )
                return CompletionResult(
                    content=cache_hit.entry.response,
                    model=cache_hit.entry.model_id,
                    metadata={
                        "cache_hit": True,
                        "entry_id": cache_hit.entry.id,
                        "provider_calls": [],
                        "usage_scope": "this_run",
                    },
                )

        if deferred_summary:
            built = self.prompt_builder.build_messages_with_trace(
                task=task,
                retrieval_response=retrieval_response,
                conversation_history=conversation_history,
                model_id=model_id,
            )
            messages = built.messages

        # 4. Call LLM
        request = CompletionRequest(
            messages=messages,
            model=model_id,
        )
        started = perf_counter()
        completion = self.llm_provider.complete(request)
        completion_ms = (perf_counter() - started) * 1000
        calls = []
        summary = built.compression.provider_usage if built.compression is not None else None
        if summary is not None and built.compression is not None:
            calls.append(
                {
                    "stage": "summary",
                    "model": summary.model,
                    "requested_model": self.prompt_builder.summary_model or model_id,
                    "input_tokens": summary.input_tokens,
                    "output_tokens": summary.output_tokens,
                    "total_tokens": summary.total_tokens,
                    "latency_ms": built.compression.provider_latency_ms,
                }
            )
        calls.append(
            {
                "stage": "completion",
                "model": completion.model,
                "requested_model": model_id,
                "input_tokens": completion.input_tokens,
                "output_tokens": completion.output_tokens,
                "total_tokens": completion.total_tokens,
                "latency_ms": completion_ms,
            }
        )
        result = replace(
            completion,
            input_tokens=completion.input_tokens + (summary.input_tokens if summary else 0),
            output_tokens=completion.output_tokens + (summary.output_tokens if summary else 0),
            total_tokens=completion.total_tokens + (summary.total_tokens if summary else 0),
            metadata={**completion.metadata, "provider_calls": calls, "usage_scope": "this_run"},
        )

        # 5. Store Cache
        if cache_enabled and result.content.strip():
            self.engine.cache_store(
                query=task,
                response=result.content,
                scope_id=scope_id,
                scope_context=scope_context,
            )

        # 6. Memory Extraction (Basic Rule-based for now)
        self._extract_and_save_memory(task, result.content, scope_id, auto_extract=auto_extract)

        return result

    def _extract_and_save_memory(
        self, task: str, response: str, scope_id: str, auto_extract: bool = False
    ) -> None:
        """A simple rule-based memory extraction.

        In a real implementation, this would use a small LLM call or tool calls
        to decide what facts/preferences to save.
        """
        # MVP: Only save if the user explicitly said "remember" or "記住"
        task_lower = task.lower()
        if "remember" in task_lower or "記住" in task_lower:
            # Just save the user's task as semantic memory for now
            self.engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id=scope_id,
                content=task,
                source_type=SourceType.USER,
                importance=0.8,
            )

        if auto_extract:
            keywords = [
                "decided",
                "chose",
                "preference",
                "constraint",
                "rule",
                "limit",
                "always",
                "never",
                "決定",
                "選擇",
                "偏好",
                "限制",
                "規則",
                "必須",
                "不可以",
            ]
            sentences = re.split(r"(?<=[。！？.!?])\s*|(?<=\n)", response)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                sentence_lower = sentence.lower()
                if any(kw in sentence_lower for kw in keywords):
                    self.engine.remember(
                        memory_type=MemoryType.EPISODIC,
                        scope_id=scope_id,
                        content=sentence,
                        source_type=SourceType.LLM,
                        source_ref=task,
                        importance=0.5,
                        confidence=0.7,
                    )
