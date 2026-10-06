"""Verify copied skill assets and run scoped JSON requests without remote APIs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from experiments.package_skill import ROOT, SKILL_PATH


def verify_installed_skill(skill: Path, *, repo: Path = ROOT) -> dict[str, object]:
    skill = skill.resolve()
    source = repo / SKILL_PATH
    verified = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        copied = skill / path.relative_to(source)
        if not copied.is_file() or copied.read_bytes() != path.read_bytes():
            raise ValueError(f"missing or changed installed skill file: {path.relative_to(source)}")
        verified += 1
    with tempfile.TemporaryDirectory(prefix="memlite-skill-smoke-") as temporary:
        database = Path(temporary) / "tutorial.db"
        memory_id = ""
        for operation in ("remember", "retrieve", "list"):
            completed = subprocess.run(
                [
                    sys.executable,
                    str(skill / "scripts/memory_tool.py"),
                    "--repo",
                    str(repo),
                    "--db",
                    str(database),
                    "--request-file",
                    str(skill / f"assets/requests/{operation}.json"),
                ],
                cwd=temporary,
                capture_output=True,
                check=True,
                timeout=60,
            )
            response = json.loads(completed.stdout)
            if response.get("ok") is not True:
                raise ValueError(f"installed helper failed: {operation}")
            result = response["result"]
            if operation == "remember":
                memory_id = result["memory"]["id"]
            elif operation == "retrieve":
                if result["selected_memory_ids"] != [memory_id]:
                    raise ValueError("installed helper did not retrieve the saved memory")
            elif [item["id"] for item in result["memories"]] != [memory_id]:
                raise ValueError("installed helper did not list the saved memory")
    return {"ok": True, "verified_files": verified, "operations": 3, "remote_calls": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-directory", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args()
    print(
        json.dumps(verify_installed_skill(args.skill_directory, repo=args.repo.resolve()), indent=2)
    )


if __name__ == "__main__":
    main()
