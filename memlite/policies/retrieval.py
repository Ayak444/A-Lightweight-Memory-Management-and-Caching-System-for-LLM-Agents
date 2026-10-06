from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from memlite.embeddings.base import EmbeddingProvider
from memlite.models import MemoryItem, MemoryStatus, MemoryType, utc_now
from memlite.storage.base import MemoryStore
from memlite.vector.base import VectorIndex


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(value, maximum))


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    candidate_limit: int = 20
    max_results: int = 5
    token_budget: int = 500
    min_similarity: float = 0.05
    similarity_weight: float = 0.55
    recency_weight: float = 0.15
    importance_weight: float = 0.15
    confidence_weight: float = 0.10
    frequency_weight: float = 0.05
    recency_half_life_days: float = 30.0
    candidate_scan_limit: int | None = None

    def __post_init__(self) -> None:
        if self.candidate_limit < 1:
            raise ValueError("candidate_limit must be at least one")
        if self.candidate_scan_limit is not None and (
            type(self.candidate_scan_limit) is not int
            or self.candidate_scan_limit < self.candidate_limit
        ):
            raise ValueError("candidate_scan_limit must be an integer >= candidate_limit")
        if self.max_results < 1:
            raise ValueError("max_results must be at least one")
        if self.token_budget < 1:
            raise ValueError("token_budget must be at least one")
        if not math.isfinite(self.min_similarity) or not 0.0 <= self.min_similarity <= 1.0:
            raise ValueError("min_similarity must be finite and between 0 and 1")
        if not math.isfinite(self.recency_half_life_days) or self.recency_half_life_days <= 0:
            raise ValueError("recency_half_life_days must be finite and positive")
        weights = (
            self.similarity_weight,
            self.recency_weight,
            self.importance_weight,
            self.confidence_weight,
            self.frequency_weight,
        )
        if any(not math.isfinite(weight) or weight < 0 for weight in weights):
            raise ValueError("retrieval weights must be finite and non-negative")
        if not math.isclose(sum(weights), 1.0, abs_tol=1e-9):
            raise ValueError("non-negative retrieval weights must sum to 1.0")


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    similarity: float
    recency: float
    importance: float
    confidence: float
    frequency: float
    pollution_penalty: float
    final_score: float

    def to_dict(self) -> dict[str, float]:
        return {
            "similarity": self.similarity,
            "recency": self.recency,
            "importance": self.importance,
            "confidence": self.confidence,
            "frequency": self.frequency,
            "pollution_penalty": self.pollution_penalty,
            "final_score": self.final_score,
        }


@dataclass(slots=True)
class RetrievalCandidate:
    memory: MemoryItem
    score: ScoreBreakdown
    estimated_tokens: int
    selected: bool = False
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory": self.memory.to_dict(),
            "score": self.score.to_dict(),
            "estimated_tokens": self.estimated_tokens,
            "selected": self.selected,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True, slots=True)
class RetrievalResponse:
    query: str
    scope_id: str
    candidates: list[RetrievalCandidate]
    selected_memory_ids: list[str]
    selected_tokens: int
    search_rounds: int = 0
    scanned_hits: int = 0
    search_limit: int = 0
    scan_limit_reached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "scope_id": self.scope_id,
            "candidate_count": len(self.candidates),
            "selected_memory_ids": self.selected_memory_ids,
            "selected_tokens": self.selected_tokens,
            "search_rounds": self.search_rounds,
            "scanned_hits": self.scanned_hits,
            "search_limit": self.search_limit,
            "scan_limit_reached": self.scan_limit_reached,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


class RetrievalService:
    def __init__(
        self,
        *,
        store: MemoryStore,
        embedding_provider: EmbeddingProvider,
        vector_index: VectorIndex,
        config: RetrievalConfig | None = None,
    ) -> None:
        self._store = store
        self._embedding_provider = embedding_provider
        self._vector_index = vector_index
        self._config = config or RetrievalConfig()

    def retrieve(
        self,
        query: str,
        *,
        scope_id: str,
        memory_types: set[MemoryType] | None = None,
    ) -> RetrievalResponse:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not scope_id.strip():
            raise ValueError("scope_id must not be empty")

        if memory_types is not None and not memory_types:
            return RetrievalResponse(query, scope_id, [], [], 0)

        query_vector = self._embedding_provider.embed([query])[0]
        now = utc_now()
        candidates: list[RetrievalCandidate] = []
        seen_ids: set[str] = set()
        search_limit = self._config.candidate_limit
        scan_limit = self._config.candidate_scan_limit or max(100_000, search_limit)
        search_rounds = 0
        # Stale index rows must not consume the usable metadata candidate budget.
        # Grow the ranked prefix without changing the vector adapter's public API.
        while True:
            hits = self._vector_index.search(
                query_vector,
                scope_id=scope_id,
                model_id=self._embedding_provider.model_id,
                memory_types=memory_types,
                limit=search_limit,
            )[:search_limit]
            search_rounds += 1
            for hit in hits:
                if hit.memory_id in seen_ids or not math.isfinite(hit.similarity):
                    continue
                seen_ids.add(hit.memory_id)
                memory = self._store.get(hit.memory_id)
                if (
                    memory is None
                    or memory.status is not MemoryStatus.ACTIVE
                    or memory.is_expired(now)
                ):
                    continue
                # Derived index metadata cannot authorize access to the source record.
                if memory.scope_id != scope_id:
                    continue
                if memory_types is not None and memory.memory_type not in memory_types:
                    continue
                candidates.append(
                    RetrievalCandidate(
                        memory=memory,
                        score=self._score(memory, hit.similarity, now),
                        estimated_tokens=estimate_tokens(memory.content),
                    )
                )
                if len(candidates) >= self._config.candidate_limit:
                    break
            if (
                len(candidates) >= self._config.candidate_limit
                or len(hits) < search_limit
                or search_limit >= scan_limit
            ):
                break
            search_limit = min(search_limit * 2, scan_limit)

        scan_limit_reached = (
            len(candidates) < self._config.candidate_limit
            and search_limit == scan_limit
            and len(hits) == search_limit
        )

        candidates.sort(key=lambda candidate: (-candidate.score.final_score, candidate.memory.id))
        selected_ids: list[str] = []
        selected_tokens = 0
        selected_count = 0
        for candidate in candidates:
            if candidate.score.similarity < self._config.min_similarity:
                candidate.rejection_reason = "below_similarity_threshold"
                continue
            if selected_count >= self._config.max_results:
                candidate.rejection_reason = "max_results_reached"
                continue
            if selected_tokens + candidate.estimated_tokens > self._config.token_budget:
                candidate.rejection_reason = "token_budget_exceeded"
                continue

            candidate.selected = True
            selected_count += 1
            selected_tokens += candidate.estimated_tokens
            selected_ids.append(candidate.memory.id)
            self._store.touch(candidate.memory.id, now)

        return RetrievalResponse(
            query=query,
            scope_id=scope_id,
            candidates=candidates,
            selected_memory_ids=selected_ids,
            selected_tokens=selected_tokens,
            search_rounds=search_rounds,
            scanned_hits=len(hits),
            search_limit=search_limit,
            scan_limit_reached=scan_limit_reached,
        )

    def _score(
        self,
        memory: MemoryItem,
        similarity: float,
        now: datetime,
    ) -> ScoreBreakdown:
        similarity_score = _clamp(similarity)
        age_days = max(0.0, (now - memory.updated_at).total_seconds() / 86_400)
        recency = math.pow(0.5, age_days / self._config.recency_half_life_days)
        frequency = _clamp(math.log1p(memory.access_count) / math.log1p(20))
        raw_penalty = memory.metadata.get("pollution_penalty", 0.0)
        pollution_penalty = _clamp(float(raw_penalty))
        final_score = _clamp(
            self._config.similarity_weight * similarity_score
            + self._config.recency_weight * recency
            + self._config.importance_weight * memory.importance
            + self._config.confidence_weight * memory.confidence
            + self._config.frequency_weight * frequency
            - pollution_penalty
        )
        return ScoreBreakdown(
            similarity=similarity_score,
            recency=recency,
            importance=memory.importance,
            confidence=memory.confidence,
            frequency=frequency,
            pollution_penalty=pollution_penalty,
            final_score=final_score,
        )


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))
