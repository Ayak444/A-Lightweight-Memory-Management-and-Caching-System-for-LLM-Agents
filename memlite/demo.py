"""End-to-end task sequence demo (PROJECT_GUIDE §2.2 scenario).

This script runs the 6-step example from the project guide using the
FakeLLMProvider so it works offline without API keys.

Usage:
    python -m memlite.demo
"""

from __future__ import annotations

import argparse
import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import TypedDict

from memlite.agent.loop import AgentLoop
from memlite.agent.prompt_builder import PromptBuilder
from memlite.engine import MemLiteEngine
from memlite.providers.fake import FakeLLMProvider

SCOPE_ID = "demo-user"


class DemoTask(TypedDict):
    step: int
    task: str
    description: str


TASK_SEQUENCE: list[DemoTask] = [
    {
        "step": 1,
        "task": "記住：專案只能使用 MIT 或 Apache-2.0 授權套件。",
        "description": "記住授權限制",
    },
    {
        "step": 2,
        "task": (
            "根據以下假設比較方案：Chroma（MIT、本地）、"
            "Qdrant（Apache-2.0、伺服器）、Milvus（Apache-2.0、Docker）。"
        ),
        "description": "比較向量資料庫",
    },
    {
        "step": 3,
        "task": "延續前面的授權限制，請推薦其中一個向量資料庫方案。",
        "description": "推薦方案（應參考授權限制記憶）",
    },
    {
        "step": 4,
        "task": "記住：部署環境不允許常駐外部資料庫。請更新這個限制。",
        "description": "更新部署限制",
    },
    {
        "step": 5,
        "task": "根據目前所有限制，再次推薦向量資料庫方案。",
        "description": "重新推薦（應使用更新後的限制）",
    },
    {
        "step": 6,
        "task": "哪些套件的開源授權是可以使用的？",
        "description": "語義改寫的問題（測試 semantic cache）",
    },
]


def run_demo(data_dir: str | Path | None = None, *, reveal_path: bool = True) -> None:
    """Execute the 6-step demo scenario."""
    if data_dir is None:
        with tempfile.TemporaryDirectory(prefix="memlite-demo-") as temporary:
            run_demo(temporary, reveal_path=reveal_path)
        return
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "demo.db"

    print("=" * 60)
    print(" MemLite-Agent  End-to-End Demo")
    location = str(data_dir) if reveal_path else "<isolated temporary database; removed after demo>"
    print(f" Data directory: {location}")
    print("=" * 60)
    print()

    with MemLiteEngine(db_path) as engine:
        llm = FakeLLMProvider()
        prompt_builder = PromptBuilder(
            system_instruction=(
                "You are a helpful research assistant. "
                "Use the provided memory context to inform your answers."
            )
        )
        agent = AgentLoop(engine, llm, prompt_builder)

        for task_info in TASK_SEQUENCE:
            step = task_info["step"]
            task = task_info["task"]
            desc = task_info["description"]

            print(f"─── Step {step}: {desc} ───")
            print(f"  User: {task}")

            result = agent.run(task, scope_id=SCOPE_ID)

            print(f"  Agent: {result.content}")
            print(f"  [tokens: in={result.input_tokens}, out={result.output_tokens}]")

            # Show memory state after each step
            active_count = len(engine._store.list_active(scope_id=SCOPE_ID, limit=100_000))
            print(f"  [active memories in scope: {active_count}]")

            # Show cache state
            stats = engine.cache_stats()
            print(
                f"  [cache: total={stats.total_entries}, hits={stats.hits}, misses={stats.misses}]"
            )
            print()

    print("=" * 60)
    print(" Demo completed.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save the offline demo as UTF-8 text")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output is None:
        run_demo()
    else:
        if args.output.exists() and not args.overwrite:
            parser.error("output exists; use --overwrite to replace it explicitly")
        capture = io.StringIO()
        with redirect_stdout(capture):
            run_demo(reveal_path=False)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(capture.getvalue(), encoding="utf-8")
        print("UTF-8 offline demo exported.")
