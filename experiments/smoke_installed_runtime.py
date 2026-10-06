"""Check an installed wheel in an isolated interpreter, without editable imports."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import memlite
from memlite.agent.loop import AgentLoop
from memlite.agent.prompt_builder import PromptBuilder
from memlite.engine import MemLiteEngine
from memlite.models import MemoryType
from memlite.policies.retrieval import RetrievalConfig
from memlite.providers import CompletionRequest, CompletionResult
from memlite.skill_cli import execute_request


class OfflineUsageProvider:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        summary = len(request.messages) == 1
        return CompletionResult(
            content="SQLite." if summary else "We decided SQLite is the database.",
            model=request.model,
            input_tokens=20 if summary else 7,
            output_tokens=2 if summary else 3,
        )


def main() -> None:
    module_path = Path(memlite.__file__).resolve()
    if not module_path.is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError("expected a wheel installed under the selected Python prefix")
    with tempfile.TemporaryDirectory(prefix="memlite-wheel-smoke-") as temporary:
        database = Path(temporary) / "memory.db"
        for iteration in range(3):
            scope = f"project:wheel-{iteration}"
            old = execute_request(
                database,
                {
                    "operation": "remember",
                    "scope": scope,
                    "content": "SQLite 儲存記憶",
                    "ttl_seconds": 3600,
                },
            )["memory"]
            retrieved = execute_request(
                database, {"operation": "retrieve", "scope": scope, "query": "SQLite 儲存記憶"}
            )
            if retrieved["selected_memory_ids"] != [old["id"]]:
                raise AssertionError("installed retrieval did not select the saved memory")
            new = execute_request(
                database,
                {
                    "operation": "supersede",
                    "scope": scope,
                    "memory_id": old["id"],
                    "content": "PostgreSQL 儲存記憶",
                    "source_ref": "offline installation check",
                },
            )["memory"]
            if new["expires_at"] != old["expires_at"]:
                raise AssertionError("installed correction changed TTL")
            if execute_request(database, {"operation": "list", "scope": "project:unrelated"})[
                "memories"
            ]:
                raise AssertionError("cross-scope memory leaked")
            execute_request(
                database, {"operation": "forget", "scope": scope, "memory_id": new["id"]}
            )
            if execute_request(database, {"operation": "list", "scope": scope})["memories"]:
                raise AssertionError("forgotten record is still active")
        provider = OfflineUsageProvider()
        with MemLiteEngine(
            database, retrieval_config=RetrievalConfig(min_similarity=0.0, token_budget=5000)
        ) as engine:
            engine.remember(
                memory_type=MemoryType.SEMANTIC,
                scope_id="installed-summary",
                content="SQLite database. " + "background information. " * 30,
            )
            agent = AgentLoop(
                engine,
                provider,
                PromptBuilder(memory_token_budget=8, compression_strategy="abstractive"),
            )
            first = agent.run("SQLite database", "installed-summary", model_id="offline-model")
            second = agent.run(
                "SQLite database", "installed-summary", model_id="offline-model", auto_extract=True
            )
            if first.total_tokens != 32 or provider.calls != 2:
                raise AssertionError("installed L3 call accounting or cache path is stale")
            if not second.metadata.get("cache_hit") or second.total_tokens != 0:
                raise AssertionError("installed L3 cache did not avoid provider calls")
            if len(engine.list_memories(scope_id="installed-summary")) != 2:
                raise AssertionError("installed cache hit skipped authorized extraction")
    print(
        json.dumps(
            {
                "ok": True,
                "iterations": 3,
                "python": sys.version.split()[0],
                "module": str(module_path),
                "scope_isolation": True,
                "ttl_preserved": True,
                "l3_accounting_and_cache": True,
                "cache_hit_extraction": True,
                "remote_calls": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
