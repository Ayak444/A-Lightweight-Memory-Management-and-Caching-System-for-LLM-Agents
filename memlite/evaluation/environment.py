"""Capture reproducible environment metadata for experiment runs."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def capture_environment(project_root: str | Path | None = None) -> dict[str, Any]:
    """Return a dict of environment details for experiment reproducibility.

    Includes git commit, Python version, key package versions, OS info,
    and a timestamp.
    """
    env: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }

    # Git info
    git_commit = _run_git("rev-parse", "HEAD", cwd=project_root)
    env["git_commit"] = git_commit.strip() if git_commit else None
    git_dirty = _run_git("status", "--porcelain", cwd=project_root)
    env["git_dirty"] = bool(git_dirty.strip()) if git_dirty is not None else None
    git_branch = _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=project_root)
    env["git_branch"] = git_branch.strip() if git_branch else None

    # Package versions
    env["packages"] = {}
    for package in ("memlite-agent", "openai", "tiktoken"):
        try:
            from importlib.metadata import version as get_version

            env["packages"][package] = get_version(package)
        except Exception:
            env["packages"][package] = None

    return env


def save_environment(
    output_path: str | Path,
    project_root: str | Path | None = None,
) -> Path:
    """Capture environment and write to a JSON file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    env = capture_environment(project_root)
    path.write_text(json.dumps(env, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _run_git(*args: str, cwd: str | Path | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None
