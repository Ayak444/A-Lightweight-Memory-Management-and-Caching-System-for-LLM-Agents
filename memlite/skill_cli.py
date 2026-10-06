"""A local, scope-explicit JSON bridge for the MemLite Codex skill."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any

from memlite.engine import MemLiteEngine
from memlite.models import MemoryStatus, MemoryType, SourceType


def _text(request: dict[str, Any], key: str) -> str:
    value = request.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a nonempty string")
    return value.strip()


def _integer(request: dict[str, Any], key: str, default: int | None = None) -> int | None:
    value = request.get(key, default)
    if value is not None and (type(value) is not int or value < 1):
        raise ValueError(f"{key} must be a positive integer")
    return value


def _number(request: dict[str, Any], key: str, default: float) -> float:
    value = request.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number between zero and one")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{key} must be a finite number between zero and one")
    return float(value)


def execute_request(database: str | Path, request: dict[str, Any]) -> dict[str, Any]:
    operation = _text(request, "operation")
    scope = _text(request, "scope")
    if operation not in {"remember", "retrieve", "list", "inspect", "supersede", "forget"}:
        raise ValueError("unsupported operation")
    optional_fields = {
        "remember": {
            "content",
            "type",
            "source",
            "source_ref",
            "importance",
            "confidence",
            "ttl_seconds",
        },
        "retrieve": {"query", "types"},
        "list": {"limit"},
        "inspect": {"memory_id"},
        "supersede": {"memory_id", "content", "source", "source_ref"},
        "forget": {"memory_id"},
    }
    unknown = set(request) - {"operation", "scope"} - optional_fields[operation]
    if unknown:
        raise ValueError(f"unsupported fields for {operation}: {', '.join(sorted(unknown))}")
    with MemLiteEngine(database) as engine:
        if operation == "remember":
            source_ref = request.get("source_ref")
            if source_ref is not None and not isinstance(source_ref, str):
                raise ValueError("source_ref must be a string")
            saved = engine.remember(
                memory_type=MemoryType(request.get("type", "semantic")),
                scope_id=scope,
                content=_text(request, "content"),
                source_type=SourceType(request.get("source", "user")),
                source_ref=source_ref,
                importance=_number(request, "importance", 0.5),
                confidence=_number(request, "confidence", 1.0),
                ttl_seconds=_integer(request, "ttl_seconds"),
            )
            return {"memory": saved.to_dict()}
        if operation == "retrieve":
            memory_types = request.get("types")
            if memory_types is not None and (
                not isinstance(memory_types, list)
                or any(not isinstance(value, str) for value in memory_types)
            ):
                raise ValueError("types must be a list of memory type strings")
            response = engine.retrieve(
                _text(request, "query"),
                scope_id=scope,
                memory_types={MemoryType(value) for value in memory_types}
                if memory_types is not None
                else None,
            )
            return response.to_dict()
        if operation == "list":
            limit = _integer(request, "limit", 20)
            if limit is None:
                raise ValueError("limit cannot be null")
            return {
                "memories": [
                    item.to_dict() for item in engine.list_memories(scope_id=scope, limit=limit)
                ]
            }
        memory_id = _text(request, "memory_id")
        item = engine.get_memory(memory_id, scope_id=scope)
        if item is None:
            raise LookupError("memory not found in requested scope")
        if operation == "inspect":
            return {"memory": item.to_dict()}
        if item.status is not MemoryStatus.ACTIVE:
            raise LookupError("memory is not active")
        if operation == "supersede":
            if item.is_expired():
                raise ValueError("expired memory cannot be superseded; create a new memory")
            source_ref = request.get("source_ref")
            if source_ref is not None and (
                not isinstance(source_ref, str) or not source_ref.strip()
            ):
                raise ValueError("correction source_ref must be a nonempty string or null")
            return {
                "memory": engine.supersede(
                    memory_id,
                    content=_text(request, "content"),
                    source_type=SourceType(request.get("source", "user")),
                    source_ref=source_ref,
                ).to_dict()
            }
        return {"memory_id": memory_id, "deleted": engine.forget(memory_id)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--request", help="JSON request; otherwise read UTF-8 JSON from stdin")
    args = parser.parse_args()
    try:
        raw = (
            args.request
            if args.request is not None
            else sys.stdin.buffer.read().decode("utf-8-sig")
        )
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        result = {"ok": True, "result": execute_request(args.db, request)}
        status = 0
    except (ValueError, TypeError, LookupError, OSError, sqlite3.Error) as error:
        result = {"ok": False, "error": str(error)}
        status = 1
    # Emit UTF-8 regardless of the host console code page.
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
