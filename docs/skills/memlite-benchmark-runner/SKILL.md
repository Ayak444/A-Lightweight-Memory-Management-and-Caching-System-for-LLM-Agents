---
name: memlite-benchmark-runner
description: Run and document reproducible offline MemLite-Agent retrieval benchmarks and controlled comparisons. Use when validating retrieval changes or experimenting with ranking and budgets.
---
Use experiments/datasets/mvp.json and memlite.benchmark_cli for a quick quality baseline; experiments/run_comparisons.py is the broader strategy/budget/corpus matrix.
Before and after a code change, keep dataset, embedding provider, and scoring configuration fixed. Record the command, Python version, dataset hash, query count, precision, recall, MRR, pass rate, and timing. Use temporary databases; do not benchmark against the user's data/memlite.db.
Write a named report under docs/ for maintained conclusions and keep raw outputs under experiments/results/ with distinct run names. Inspect metric definitions before interpreting results.
The deterministic hash provider measures offline retrieval behavior, not real semantic understanding or LLM answer success. A single timing run is descriptive, not proof of speedup; avoid performance claims without repeated measurements.
Report regressions and unchanged results honestly. Separate completed experiments from proposed cache/real-provider experiments.
