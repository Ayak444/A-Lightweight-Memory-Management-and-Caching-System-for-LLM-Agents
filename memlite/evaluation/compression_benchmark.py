"""Measure actual Agent prompt fact retention, not fake LLM answer quality."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import tempfile
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from memlite.agent.loop import AgentLoop
from memlite.agent.prompt_builder import PromptBuilder
from memlite.engine import MemLiteEngine
from memlite.evaluation.environment import save_environment
from memlite.models import MemoryType
from memlite.policies.compression import extractive_compress
from memlite.policies.retrieval import RetrievalConfig
from memlite.providers import CompletionRequest, CompletionResult

BUDGETS = (None, 8, 16, 32, 64, 128)


class PromptRecorder:
    def __init__(self) -> None:
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        return CompletionResult(content="offline trace; not an evaluated answer")


def validate_dataset(dataset: dict[str, Any]) -> None:
    if dataset.get("version") != "compression-1.0.0":
        raise ValueError("expected compression-1.0.0")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be nonempty")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or any(
            not isinstance(case.get(key), str) or not case[key].strip()
            for key in ("id", "query", "content")
        ):
            raise ValueError("case id, query and content must be nonempty strings")
        if case["id"] in ids:
            raise ValueError("duplicate case id")
        ids.add(case["id"])
        required = case.get("required")
        if (
            not isinstance(required, list)
            or not required
            or any(
                not isinstance(fact, str) or not fact or fact not in case["content"]
                for fact in required
            )
            or len(set(required)) != len(required)
        ):
            raise ValueError("required facts must be unique nonempty substrings of source content")


def run_compression_benchmark(
    dataset_path: str | Path,
    output_directory: str | Path,
    *,
    repeats: int = 3,
) -> dict[str, Any]:
    if type(repeats) is not int or repeats < 3:
        raise ValueError("require at least three repetitions")
    path, output = Path(dataset_path), Path(output_directory)
    dataset = json.loads(path.read_text(encoding="utf-8"))
    validate_dataset(dataset)
    config = RetrievalConfig(max_results=1, min_similarity=0.0, token_budget=5000)
    if any(math.ceil(len(case["content"].encode()) / 4) > 5000 for case in dataset["cases"]):
        raise ValueError("source exceeds predeclared L1 budget")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("choose an empty/new output directory")
    traces: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="memlite-compression-") as temporary:
        for repetition in range(repeats):
            for index, case in enumerate(dataset["cases"]):
                for budget in BUDGETS:
                    recorder = PromptRecorder()
                    database = Path(temporary) / f"{repetition}-{index}-{budget}.db"
                    with MemLiteEngine(database, retrieval_config=config) as engine:
                        item = engine.remember(
                            memory_type=MemoryType.SEMANTIC,
                            scope_id=case["id"],
                            content=case["content"],
                        )
                        agent = AgentLoop(
                            engine, recorder, PromptBuilder(memory_token_budget=budget)
                        )
                        agent.run(case["query"], case["id"], use_cache=False)
                        saved = engine.get_memory(item.id, scope_id=case["id"])
                        unchanged = saved is not None and saved.content == case["content"]
                    request = recorder.requests[0]
                    memory_context = "\n".join(
                        message["content"] for message in request.messages[1:-1]
                    )
                    original = f"- {case['content']}"
                    payload = (
                        original
                        if budget is None
                        else extractive_compress(
                            original, case["query"], token_budget=budget
                        ).compressed_text
                    )
                    if payload and payload not in memory_context:
                        raise AssertionError(
                            "compression trace does not match the actual Agent prompt"
                        )
                    kept = [fact for fact in case["required"] if fact in memory_context]
                    original_tokens = math.ceil(len(original.encode()) / 4)
                    payload_tokens = math.ceil(len(payload.encode()) / 4)
                    traces.append(
                        {
                            "case_id": case["id"],
                            "repeat": repetition + 1,
                            "strategy": "full_selected_context"
                            if budget is None
                            else f"extractive_{budget}",
                            "budget": budget,
                            "required": case["required"],
                            "kept": kept,
                            "dropped": [fact for fact in case["required"] if fact not in kept],
                            "fact_retention": len(kept) / len(case["required"]),
                            "all_facts_retained": len(kept) == len(case["required"]),
                            "original_payload_tokens_estimate": original_tokens,
                            "payload_tokens_estimate": payload_tokens,
                            "payload_ratio": payload_tokens / original_tokens,
                            "prompt_tokens_estimate": sum(
                                math.ceil(len(message["content"].encode()) / 4)
                                for message in request.messages
                            ),
                            "memory_context": memory_context,
                            "source_unchanged": unchanged,
                            "provider_calls": len(recorder.requests),
                            "budget_violation": budget is not None and payload_tokens > budget,
                        }
                    )
    results = []
    for strategy in dict.fromkeys(row["strategy"] for row in traces):
        rows = [row for row in traces if row["strategy"] == strategy]
        results.append(
            {"strategy": strategy, "unique_cases": len(dataset["cases"])}
            | {
                f"mean_{metric}": statistics.mean(row[metric] for row in rows)
                for metric in (
                    "fact_retention",
                    "all_facts_retained",
                    "payload_ratio",
                    "payload_tokens_estimate",
                    "prompt_tokens_estimate",
                )
            }
        )
    report = {
        "dataset_version": dataset["version"],
        "dataset_sha256": sha256(path.read_bytes()).hexdigest(),
        "case_count": len(dataset["cases"]),
        "repeats": repeats,
        "trace_count": len(traces),
        "budgets": BUDGETS,
        "retrieval_config": asdict(config),
        "repeat_context_stable": all(
            len(
                {
                    row["memory_context"]
                    for row in traces
                    if row["case_id"] == case["id"] and row["budget"] == budget
                }
            )
            == 1
            for case in dataset["cases"]
            for budget in BUDGETS
        ),
        "budget_violations": sum(row["budget_violation"] for row in traces),
        "source_mutations": sum(not row["source_unchanged"] for row in traces),
        "results": results,
        "source_sha256": {
            str(source.relative_to(Path(__file__).resolve().parents[2])).replace("\\", "/"): sha256(
                source.read_bytes()
            ).hexdigest()
            for source in sorted(Path(__file__).resolve().parents[1].rglob("*.py"))
        },
        "notes": [
            "Required labels are not sent to retrieval, compression, or the provider.",
            "One source per case with permissive L1 selection isolates the downstream L2 effect.",
            "Exact substring retention is a proxy, not semantic correctness or LLM task success.",
            "Token estimates use ceil(UTF-8 bytes/4), not tokenizer or paid usage.",
            "Prompt estimate includes text instructions but excludes model framing overhead.",
            "Repeats test determinism, not independent samples; cases are authored stress tests.",
            "Whitespace overlap can fail on Chinese and differently worded queries.",
            "L3, real provider quality, costs and latency are not measured.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    for filename, value in (("compression_report.json", report), ("query_traces.json", traces)):
        (output / filename).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    (output / "dataset_snapshot.json").write_bytes(path.read_bytes())
    with (output / "compression_comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    save_environment(output / "environment.json", Path.cwd())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=Path("experiments/datasets/compression.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    report = run_compression_benchmark(args.dataset, args.output, repeats=args.repeats)
    print(json.dumps({"traces": report["trace_count"], "results": report["results"]}, indent=2))


if __name__ == "__main__":
    main()
