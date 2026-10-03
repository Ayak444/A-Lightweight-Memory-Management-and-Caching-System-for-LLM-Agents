from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from memlite.manager import MemoryManager, MemoryNotFoundError
from memlite.models import MemoryItem, MemoryType, SourceType
from memlite.storage.sqlite import SQLiteMemoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memlite",
        description="Inspect and manage MemLite-Agent memories.",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("MEMLITE_DB_PATH", "data/memlite.db"),
        help="SQLite database path (default: data/memlite.db)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize the SQLite database")

    remember = subparsers.add_parser("remember", help="Store a memory")
    remember.add_argument("--scope", required=True)
    remember.add_argument("--type", choices=_enum_values(MemoryType), required=True)
    remember.add_argument("--content", required=True)
    remember.add_argument("--source", choices=_enum_values(SourceType), default="user")
    remember.add_argument("--importance", type=float, default=0.5)
    remember.add_argument("--confidence", type=float, default=1.0)
    remember.add_argument("--ttl", type=int, help="Time to live in seconds")

    recall = subparsers.add_parser("recall", help="List active memories for a scope")
    recall.add_argument("--scope", required=True)
    recall.add_argument("--type", choices=_enum_values(MemoryType), action="append")
    recall.add_argument("--limit", type=int, default=20)

    supersede = subparsers.add_parser("supersede", help="Replace an active memory")
    supersede.add_argument("memory_id")
    supersede.add_argument("--content", required=True)

    forget = subparsers.add_parser("forget", help="Soft-delete an active memory")
    forget.add_argument("memory_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = SQLiteMemoryStore(Path(args.db))
    manager = MemoryManager(store)

    try:
        if args.command == "init":
            print(json.dumps({"database": str(store.database_path), "initialized": True}))
            return 0

        if args.command == "remember":
            item = manager.remember(
                memory_type=MemoryType(args.type),
                scope_id=args.scope,
                content=args.content,
                source_type=SourceType(args.source),
                importance=args.importance,
                confidence=args.confidence,
                ttl_seconds=args.ttl,
            )
            _print_json(item)
            return 0

        if args.command == "recall":
            memory_types = {MemoryType(value) for value in args.type} if args.type else None
            items = manager.recall(
                scope_id=args.scope,
                memory_types=memory_types,
                limit=args.limit,
            )
            print(json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2))
            return 0

        if args.command == "supersede":
            try:
                item = manager.supersede(args.memory_id, content=args.content)
            except MemoryNotFoundError as error:
                parser.error(str(error))
            _print_json(item)
            return 0

        if args.command == "forget":
            deleted = manager.forget(args.memory_id)
            print(json.dumps({"memory_id": args.memory_id, "deleted": deleted}))
            return 0 if deleted else 1
    finally:
        manager.close()

    parser.error(f"unknown command: {args.command}")
    return 2


def _enum_values(enum_type: type[MemoryType] | type[SourceType]) -> list[str]:
    return [member.value for member in enum_type]


def _print_json(item: MemoryItem) -> None:
    print(json.dumps(item.to_dict(), ensure_ascii=False, indent=2))
