"""Forward UTF-8 JSON to an existing MemLite checkout with an explicit database."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--request-file", type=Path, required=True)
    args = parser.parse_args()
    repo = (args.repo or Path(os.environ.get("MEMLITE_REPO", Path.cwd()))).resolve()
    if not (repo / "memlite/skill_cli.py").is_file() or not (repo / "pyproject.toml").is_file():
        parser.error("specify a MemLite checkout using --repo or MEMLITE_REPO")
    database = args.db or repo / "data/skill-memory.db"
    if not database.is_absolute():
        database = repo / database
    database = database.resolve()
    try:
        request = json.loads(args.request_file.read_text(encoding="utf-8-sig"))
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"MemLite database: {database}", file=sys.stderr)
    result = subprocess.run(
        [sys.executable, "-m", "memlite.skill_cli", "--db", str(database)],
        cwd=repo,
        input=payload,
        capture_output=True,
        check=False,
    )
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
