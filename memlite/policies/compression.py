"""Context compression strategies.

Three levels of compression, from cheapest to most powerful:

- L1: Token-budget selection (already in retrieval.py)
- L2: Extractive compression — keep only the most query-relevant sentences
- L3: Abstractive summary — use an LLM to produce a condensed summary
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from time import perf_counter

from memlite.providers import CompletionRequest, CompletionResult, LLMProvider


@dataclass(frozen=True, slots=True)
class CompressionResult:
    """Result of a compression operation."""

    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    strategy: str  # "extractive" or "abstractive"
    provider_usage: CompletionResult | None = None
    provider_latency_ms: float = 0.0

    @property
    def compression_ratio(self) -> float:
        if self.original_tokens == 0:
            return 1.0
        return self.compressed_tokens / self.original_tokens


def _estimate_tokens(text: str) -> int:
    return math.ceil(len(text.encode("utf-8")) / 4)


# ---------------------------------------------------------------------------
# L2: Extractive compression
# ---------------------------------------------------------------------------

_SENTENCE_RE = re.compile(r"(?<=[。！？.!?])\s*|(?<=\n)")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using punctuation and newlines."""
    parts = _SENTENCE_RE.split(text)
    return [s.strip() for s in parts if s.strip()]


def _word_overlap_score(sentence: str, query: str) -> float:
    """Compute a cheap relevance score based on token overlap."""
    sentence_tokens = set(sentence.lower().split())
    query_tokens = set(query.lower().split())
    if not query_tokens:
        return 0.0
    return len(sentence_tokens & query_tokens) / len(query_tokens)


def extractive_compress(
    text: str,
    query: str,
    *,
    token_budget: int = 200,
    min_score: float = 0.0,
) -> CompressionResult:
    """Keep only the sentences most relevant to *query* within *token_budget*.

    Sentences are ranked by word-overlap with the query and greedily selected
    in order of relevance until the budget is exhausted.
    """
    if token_budget < 1:
        raise ValueError("token_budget must be positive")
    if not math.isfinite(min_score) or not 0.0 <= min_score <= 1.0:
        raise ValueError("min_score must be finite and between zero and one")
    original_tokens = _estimate_tokens(text)
    sentences = _split_sentences(text)

    if not sentences:
        return CompressionResult(
            original_text=text,
            compressed_text=text,
            original_tokens=original_tokens,
            compressed_tokens=original_tokens,
            strategy="extractive",
        )

    scored = sorted(
        ((s, _word_overlap_score(s, query)) for s in sentences),
        key=lambda pair: -pair[1],
    )

    selected: list[str] = []
    for sentence, score in scored:
        if score < min_score:
            continue
        if sentence in selected:
            continue
        if _estimate_tokens(" ".join([*selected, sentence])) > token_budget:
            continue
        selected.append(sentence)

    # Restore original order for readability
    original_order = {s: i for i, s in enumerate(sentences)}
    selected.sort(key=lambda s: original_order.get(s, 0))

    compressed_text = " ".join(selected)
    return CompressionResult(
        original_text=text,
        compressed_text=compressed_text,
        original_tokens=original_tokens,
        compressed_tokens=_estimate_tokens(compressed_text),
        strategy="extractive",
    )


# ---------------------------------------------------------------------------
# L3: Abstractive summary
# ---------------------------------------------------------------------------

_SUMMARIZE_PROMPT = (
    "Summarize the following text concisely. "
    "Preserve all key facts, numbers, names, and dates. "
    "Keep it under {budget} tokens.\n\n"
    "Text:\n{text}"
)


def abstractive_compress(
    text: str,
    llm_provider: LLMProvider,
    *,
    token_budget: int = 200,
    model: str = "",
) -> CompressionResult:
    """Use an LLM to produce an abstractive summary of *text*.

    This incurs an additional LLM call.  The cost should be tracked separately
    from the main task completion call.
    """
    if token_budget < 1:
        raise ValueError("token_budget must be positive")
    original_tokens = _estimate_tokens(text)

    # Skip if already short enough
    if original_tokens <= token_budget:
        return CompressionResult(
            original_text=text,
            compressed_text=text,
            original_tokens=original_tokens,
            compressed_tokens=original_tokens,
            strategy="abstractive",
        )

    prompt = _SUMMARIZE_PROMPT.format(budget=token_budget, text=text)
    started = perf_counter()
    result = llm_provider.complete(
        CompletionRequest(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            max_tokens=token_budget,
        )
    )
    latency_ms = (perf_counter() - started) * 1000
    compressed_text = result.content.strip()
    if not compressed_text or _estimate_tokens(compressed_text) > token_budget:
        raise ValueError("summary is empty or exceeds the estimated token budget")
    return CompressionResult(
        original_text=text,
        compressed_text=compressed_text,
        original_tokens=original_tokens,
        compressed_tokens=_estimate_tokens(compressed_text),
        strategy="abstractive",
        provider_usage=result,
        provider_latency_ms=latency_ms,
    )
