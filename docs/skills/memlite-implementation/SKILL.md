---
name: memlite-implementation
description: Implement, debug, test, and review MemLite-Agent memory lifecycle and retrieval changes. Use for code changes in its Python core and SQLite adapters.
---
Reproduce the affected behavior with a temporary database or a controlled provider/index double before fixing it. Tests should assert observable results and persistence, not source text.
Keep metadata scope, type, active status, and expiry authoritative at the retrieval boundary even if the vector adapter claims it filtered them. Check that rejected candidates cannot leak into traces or increment access counts. Treat duplicate and non-finite backend hits deliberately.
Exercise TTL without sleeps using fixed timestamps or mocked clocks. Preserve soft deletion and supersedes relations. Do not claim metadata/vector writes are atomic across separate databases.
Validate scoring configuration at construction; allow zero weights for ablations, reject negative/non-finite weights and invalid bounds. Maintain token-budget rejection reasons.
Run python -m unittest discover -s tests -v and the existing Ruff/mypy checks using the project's dev interpreter. Review changed call sites and public protocol compatibility. Document remaining limitations rather than broadening into unrelated refactors.
