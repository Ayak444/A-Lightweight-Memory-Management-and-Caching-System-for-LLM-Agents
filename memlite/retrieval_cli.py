from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from memlite.engine import MemLiteEngine
from memlite.models import MemoryType, SourceType


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memlite-retrieval",
        description="Manage memories and inspect explainable vector retrieval.",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("MEMLITE_DB_PATH", "data/memlite.db"),
        help="SQLite metadata database path",
    )
    parser.add_argument("--vectors", help="Optional vector index database path")
    commands = parser.add_subparsers(dest="command", required=True)

    remember = commands.add_parser("remember", help="Store and index a memory")
    remember.add_argument("--scope", required=True)
    remember.add_argument("--type", choices=[item.value for item in MemoryType], required=True)
    remember.add_argument("--content", required=True)
    remember.add_argument("--source", choices=[item.value for item in SourceType], default="user")
    remember.add_argument("--importance", type=float, default=0.5)
    remember.add_argument("--confidence", type=float, default=1.0)
    remember.add_argument("--ttl", type=int)

    retrieve = commands.add_parser("retrieve", help="Retrieve memories with a score trace")
    retrieve.add_argument("--scope", required=True)
    retrieve.add_argument("--query", required=True)
    retrieve.add_argument("--type", choices=[item.value for item in MemoryType], action="append")

    supersede = commands.add_parser("supersede", help="Replace and reindex a memory")
    supersede.add_argument("memory_id")
    supersede.add_argument("--content", required=True)

    forget = commands.add_parser("forget", help="Soft-delete a memory and remove its vector")
    forget.add_argument("memory_id")

    reindex = commands.add_parser("reindex", help="Rebuild one scope in the vector index")
    reindex.add_argument("--scope", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)
    with MemLiteEngine(
        Path(args.db),
        vector_path=Path(args.vectors) if args.vectors else None,
    ) as engine:
        if args.command == "remember":
            item = engine.remember(
                memory_type=MemoryType(args.type),
                scope_id=args.scope,
                content=args.content,
                source_type=SourceType(args.source),
                importance=args.importance,
                confidence=args.confidence,
                ttl_seconds=args.ttl,
            )
            _print_json(item.to_dict())
            return 0

        if args.command == "retrieve":
            memory_types = {MemoryType(value) for value in args.type} if args.type else None
            response = engine.retrieve(
                args.query,
                scope_id=args.scope,
                memory_types=memory_types,
            )
            _print_json(response.to_dict())
            return 0

        if args.command == "supersede":
            _print_json(engine.supersede(args.memory_id, content=args.content).to_dict())
            return 0

        if args.command == "forget":
            deleted = engine.forget(args.memory_id)
            _print_json({"memory_id": args.memory_id, "deleted": deleted})
            return 0 if deleted else 1

        if args.command == "reindex":
            indexed = engine.reindex_scope(args.scope)
            _print_json({"scope_id": args.scope, "indexed": indexed})
            return 0

    return 2


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
