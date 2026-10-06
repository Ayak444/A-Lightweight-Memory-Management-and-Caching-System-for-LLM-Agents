"""Build a reproducible, data-free Codex skill archive from this checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = Path("docs/skills/memlite-agent")
REQUIRED = (
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/memory_tool.py",
    "references/memory-protocol.md",
    "references/research-workflow.md",
)
ALLOWED_SUFFIXES = {".md", ".py", ".yaml", ".json"}


def build_skill_archive(output: Path, *, root: Path = ROOT) -> dict[str, object]:
    root = root.resolve()
    skill = root / SKILL_PATH
    for required in REQUIRED:
        if not (skill / required).is_file():
            raise ValueError(f"missing skill file: {required}")
    payload: dict[str, bytes] = {}
    for path in sorted(skill.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlinks are not distributable: {path}")
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix not in ALLOWED_SUFFIXES:
            raise ValueError(f"unexpected skill asset: {path}")
        if not path.resolve().is_relative_to(skill.resolve()):
            raise ValueError("skill file escapes its source directory")
        payload[f"memlite-agent/{path.relative_to(skill).as_posix()}"] = path.read_bytes()
    payload["LICENSE"] = (root / "LICENSE").read_bytes()
    payload["INSTALL.md"] = (root / "docs/SKILL_INSTALL.zh-TW.md").read_bytes()
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()}
    manifest: dict[str, object] = {
        "format_version": 1,
        "skill": "memlite-agent",
        "runtime": "MemLite checkout with Python >=3.11; engine not included",
        "files": hashes,
    }
    payload["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Fixed metadata makes equal inputs produce byte-identical archives.
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return {
        "output": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "file_count": len(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist/memlite-agent-skill.zip"))
    args = parser.parse_args()
    print(json.dumps(build_skill_archive(args.output), indent=2))


if __name__ == "__main__":
    main()
