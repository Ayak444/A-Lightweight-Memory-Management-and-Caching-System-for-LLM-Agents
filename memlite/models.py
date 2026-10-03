from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_content(content: str) -> str:
    return " ".join(content.split()).casefold()


def content_digest(content: str) -> str:
    return sha256(normalize_content(content).encode("utf-8")).hexdigest()


class MemoryType(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class SourceType(StrEnum):
    USER = "user"
    LLM = "llm"
    TOOL = "tool"
    SYSTEM = "system"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


@dataclass(slots=True)
class MemoryItem:
    memory_type: MemoryType
    scope_id: str
    content: str
    source_type: SourceType = SourceType.USER
    source_ref: str | None = None
    importance: float = 0.5
    confidence: float = 1.0
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    content_hash: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    last_accessed_at: datetime | None = None
    access_count: int = 0
    version: int = 1
    status: MemoryStatus = MemoryStatus.ACTIVE

    def __post_init__(self) -> None:
        self.content = self.content.strip()
        self.scope_id = self.scope_id.strip()

        if not self.content:
            raise ValueError("content must not be empty")
        if not self.scope_id:
            raise ValueError("scope_id must not be empty")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.access_count < 0:
            raise ValueError("access_count must not be negative")
        if self.version < 1:
            raise ValueError("version must be at least 1")

        if not self.content_hash:
            self.content_hash = content_digest(self.content)

        for value in (self.created_at, self.updated_at, self.expires_at, self.last_accessed_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("all datetime values must include timezone information")

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and self.expires_at <= (now or utc_now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type.value,
            "scope_id": self.scope_id,
            "content": self.content,
            "content_hash": self.content_hash,
            "source_type": self.source_type.value,
            "source_ref": self.source_ref,
            "importance": self.importance,
            "confidence": self.confidence,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_accessed_at": (
                self.last_accessed_at.isoformat() if self.last_accessed_at else None
            ),
            "access_count": self.access_count,
            "version": self.version,
            "status": self.status.value,
        }
