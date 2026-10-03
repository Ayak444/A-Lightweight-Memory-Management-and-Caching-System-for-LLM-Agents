---
name: memlite-repo-planner
description: Analyze MemLite-Agent architecture and plan bounded implementation slices from its code, tests, ADRs, and project plan. Use for this repository's planning and code exploration.
---
Read README.md, pyproject.toml, docs/PROJECT_PLAN.zh-TW.md and the relevant docs/adr files; verify progress against actual memlite/ code and tests/ because milestone prose may lag implementation.
Trace CLI -> engine/manager -> policy -> storage/vector protocols before editing. SQLite metadata is authoritative; vector indexes are rebuildable derived data. Preserve the dependency-free offline core and provider protocols.
Choose a concrete invariant and acceptance test for the next slice. Finish retrieval reliability before expanding into cache, API, or deployment. User requests can change that priority.
Check git status before editing: this repository may contain an entirely untracked implementation. Preserve existing work; do not treat untracked files as disposable.
Record remaining gaps separately from implemented behavior. Create local issue-sized work descriptions unless the user requests publishing issues.
