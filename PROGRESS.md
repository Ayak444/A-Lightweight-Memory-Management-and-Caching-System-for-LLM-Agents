# MemLite-Agent 開發進度追蹤

> **給 AI Agent 的指示**：這是本專案的進度總覽。開始任何工作前，請先讀完本文件，了解哪些已完成、哪些進行中、哪些尚未開始。完成任務後，請更新對應的狀態標記。
>
> **狀態標記**：✅ 完成 | 🔧 進行中 | ❌ 尚未開始 | ⏭️ 刻意跳過（非目標）

---

## 專案定位

- **專案名稱**：MemLite-Agent: A Lightweight Hierarchical Memory and Semantic Cache System for LLM Agents
- **核心問題**：在不降低任務成功率的前提下，分層記憶、語意快取與 context 壓縮能否降低 LLM Agent 的 token、延遲與 API 成本？
- **定位**：求職作品集 + 可量化的研究原型
- **技術棧**：Python 3.12 / SQLite / 本地向量搜尋 / FastAPI (planned)
- **完整規格**：[PROJECT_GUIDE.md](PROJECT_GUIDE.md)

---

## Milestone 總覽

| Milestone | 名稱 | 狀態 | 說明 |
|-----------|------|------|------|
| M0 | 定義與骨架 | ✅ 完成 | repo、CI、domain models、fake providers |
| M1 | 可用的 Memory Manager | ✅ 完成 | SQLite schema、CRUD、向量檢索、trace |
| M2 | Compression 與 Semantic Cache | ✅ 完成 | token-budget selection、semantic cache、eviction |
| M3 | Evaluation | 🔧 部分完成 | benchmark 基礎有了，但缺 agent loop、run log、dataset 擴充 |
| M4 | 作品集展示 | ❌ 尚未開始 | UI、demo GIF、failure analysis |
| M5 | 部署與發布 | ❌ 尚未開始 | Docker、deploy、health check |

---

## 模組詳細進度

### 核心一：Memory Lifecycle

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| MemoryItem data model | ✅ | `memlite/models.py` | 含 validation、content_hash、to_dict |
| MemoryType / SourceType / MemoryStatus enums | ✅ | `memlite/models.py` | |
| SQLiteMemoryStore (CRUD) | ✅ | `memlite/storage/sqlite.py` | save、get、list_active、touch、replace、soft_delete |
| list_expired 查詢 | ✅ | `memlite/storage/sqlite.py` | 讓 TTL eviction 能找到過期記憶 |
| MemoryStore protocol | ✅ | `memlite/storage/base.py` | 含 list_expired |
| MemoryManager (remember/recall/supersede/forget) | ✅ | `memlite/manager.py` | |
| memory_relations table (supersedes) | ✅ | `memlite/storage/sqlite.py` | 只支援 supersedes，不做完整 graph |
| 去重 (content_hash dedup) | ✅ | `memlite/storage/sqlite.py` | 同 scope/type/hash/active 才去重 |
| TTL 過期控制 | ✅ | `memlite/models.py` | is_expired() + list_active 過濾 |

### 核心二：Semantic Cache

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| CacheEntry model | ✅ | `memlite/cache.py` | query_hash、scope_fingerprint、TTL |
| ScopeContext (scope fingerprint) | ✅ | `memlite/cache.py` | hash(system_prompt, model_id, tool_schema, context) |
| Exact match lookup | ✅ | `memlite/cache.py` | 用 query_hash + scope_fingerprint |
| Semantic similarity lookup | ✅ | `memlite/cache.py` | 用 vector search + threshold |
| Scope fingerprint mismatch 拒絕 | ✅ | `memlite/cache.py` | rejected_hit event |
| TTL 過期 | ✅ | `memlite/cache.py` | |
| 手動 invalidation (single + scope) | ✅ | `memlite/cache.py` | invalidate() + invalidate_scope() |
| Hit/miss/rejected_hit 事件 log | ✅ | `memlite/cache.py` | cache_events table |
| CacheStats 統計 | ✅ | `memlite/cache.py` | total、active、hits、misses、rejected、hit_rate |
| 可調 similarity threshold | ✅ | `memlite/cache.py` | 建構參數 |

### 核心三：Evaluation 與 Observability

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| BenchmarkDataset loader + validator | ✅ | `memlite/evaluation/datasets.py` | 驗證 required categories |
| Retrieval benchmark | ✅ | `memlite/evaluation/retrieval_benchmark.py` | precision、recall、MRR、latency |
| Comparison benchmark (strategies) | ✅ | `memlite/evaluation/comparison_benchmark.py` | 多策略 + token budget + corpus latency |
| CSV / JSON 輸出 | ✅ | `memlite/evaluation/comparison_benchmark.py` | |
| Run / Event log 持久化到 SQLite | ❌ | — | PROJECT_GUIDE 要求 runs、retrieval_events、metrics table |
| B0 baseline (full history) | ❌ | — | 需要 agent loop 才能實作 |
| B1 baseline (recent window) | ❌ | — | 需要 agent loop 才能實作 |
| summary.md report 產生器 | ❌ | — | |
| Dataset 擴充到 30+ 組 | ❌ | `experiments/datasets/mvp.json` | 目前只有 10 組 |
| environment.json (git commit, versions) | ❌ | — | |

### Retrieval 與 Scoring

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| VectorIndex protocol | ✅ | `memlite/vector/base.py` | |
| SQLiteVectorIndex (exact search baseline) | ✅ | `memlite/vector/sqlite.py` | dot product similarity |
| EmbeddingProvider protocol | ✅ | `memlite/embeddings/base.py` | model_id、dimension、embed() |
| DeterministicHashEmbedding | ✅ | `memlite/embeddings/deterministic.py` | 離線可用、CJK 支援 |
| RetrievalService (hybrid scoring) | ✅ | `memlite/policies/retrieval.py` | 5 維加權 + pollution penalty |
| ScoreBreakdown (可解釋分數) | ✅ | `memlite/policies/retrieval.py` | |
| Token-budget selection | ✅ | `memlite/policies/retrieval.py` | |
| Scope isolation 安全檢查 | ✅ | `memlite/policies/retrieval.py` | vector hit 後再驗 metadata |

### Eviction Policies

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| EvictionPolicy protocol | ✅ | `memlite/policies/eviction.py` | |
| TTLEviction | ✅ | `memlite/policies/eviction.py` | 用 list_expired 查過期條目 |
| LRUEviction | ✅ | `memlite/policies/eviction.py` | 依 last_accessed_at 排序 |
| LFUEviction | ✅ | `memlite/policies/eviction.py` | 依 access_count 排序 |
| HybridEviction (TTL + LRU/LFU) | ✅ | `memlite/policies/eviction.py` | |
| Engine 整合 (eviction + vector cleanup) | ✅ | `memlite/engine.py` | run_eviction() 自動清向量 |

### Provider 抽象

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| LLMProvider protocol | ✅ | `memlite/providers/__init__.py` | CompletionRequest / CompletionResult |
| TokenCounter protocol | ✅ | `memlite/providers/__init__.py` | |
| EmbeddingProvider protocol | ✅ | `memlite/embeddings/base.py` | |
| FakeLLMProvider | ✅ | `memlite/providers/fake.py` | deterministic，不呼叫 API |
| FakeTokenCounter | ✅ | `memlite/providers/fake.py` | ceil(bytes/4) |
| DeterministicHashEmbedding | ✅ | `memlite/embeddings/deterministic.py` | |
| OpenAI adapter | ❌ | — | 真實 provider |
| 真實 embedding provider | ❌ | — | sentence-transformers 或 OpenAI |

### Agent Loop

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| agent/loop.py | ❌ | — | 最小 Agent 執行流程 |
| agent/prompt_builder.py | ❌ | — | 記憶 + 指令 + task → prompt |
| Memory extraction (LLM 結果寫回記憶) | ❌ | — | |
| 端到端 task sequence demo | ❌ | — | PROJECT_GUIDE §2.2 的 6 步情境 |

### Compression

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| Token-budget selection (L1) | ✅ | `memlite/policies/retrieval.py` | 依 score 選入直到超預算 |
| Extractive compression (L2) | ❌ | — | 只保留與 query 最相關的句子 |
| Abstractive summary (L3) | ❌ | — | 用 LLM 摘要，需要 LLMProvider |
| 獨立 compression.py 模組 | ❌ | — | |

### API 與 CLI

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| CLI: init / remember / recall / supersede / forget | ✅ | `memlite/cli.py` | |
| CLI: retrieve (with score trace) | ✅ | `memlite/retrieval_cli.py` | |
| CLI: reindex | ✅ | `memlite/retrieval_cli.py` | |
| CLI: benchmark | ✅ | `memlite/benchmark_cli.py` | |
| FastAPI: /v1/memories CRUD | ❌ | — | |
| FastAPI: /v1/retrieval/query | ❌ | — | |
| FastAPI: /v1/cache | ❌ | — | |
| FastAPI: /health | ❌ | — | |

### 部署

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| Dockerfile | ❌ | — | |
| docker-compose.yml | ❌ | — | |
| Health check endpoint | ❌ | — | |
| Rate limit / budget cap | ❌ | — | |
| Zeabur / Render 部署 | ❌ | — | |

### 文件

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| PROJECT_GUIDE.md | ✅ | `PROJECT_GUIDE.md` | 完整規格 |
| README.md | ✅ | `README.md` | 含架構圖、API 範例、限制 |
| ADR 0001: SQLite as source of truth | ✅ | `docs/adr/0001-*.md` | |
| ADR 0002: Provider-agnostic core | ✅ | `docs/adr/0002-*.md` | |
| ADR 0003: Separate metadata and vector | ✅ | `docs/adr/0003-*.md` | |
| ADR 0004: Cache scope and invalidation | ✅ | `docs/adr/0004-*.md` | |
| ADR 0005: Memory versioning and supersession | ✅ | `docs/adr/0005-*.md` | |
| ADR 0006: Evaluation baselines | ✅ | `docs/adr/0006-*.md` | |
| QUICKSTART 文件 | ✅ | `docs/QUICKSTART.zh-TW.md` | |
| Demo GIF 或截圖 | ❌ | — | |
| 失敗案例分析 | ❌ | — | |
| 代表性實驗表格 | ❌ | — | 需要跑完 B0/B1 baseline |

### 測試

| 項目 | 狀態 | 檔案 | 測試數 |
|------|------|------|--------|
| Memory Manager tests | ✅ | `tests/test_memory_manager.py` | 5 |
| Retrieval tests | ✅ | `tests/test_retrieval.py` | 5 |
| Retrieval boundary tests | ✅ | `tests/test_retrieval_boundaries.py` | 4 |
| Dataset validation test | ✅ | `tests/test_dataset.py` | 1 |
| Retrieval benchmark test | ✅ | `tests/test_retrieval_benchmark.py` | 1 |
| Comparison benchmark test | ✅ | `tests/test_comparison_benchmark.py` | 1 |
| Semantic cache tests | ✅ | `tests/test_cache.py` | 12 |
| Eviction policy tests | ✅ | `tests/test_eviction.py` | 10 |
| Provider tests | ✅ | `tests/test_providers.py` | 7 |
| **合計** | | | **46** |

---

## 研究問題對應

| 研究問題 | 可回答程度 | 缺什麼 |
|---------|-----------|--------|
| **RQ1**: Hierarchical memory 能否在維持 task success rate 的情況下降低 token usage？ | 🔧 部分 | 需要 agent loop + B0/B1 baseline |
| **RQ2**: Semantic cache 能降低多少 latency 與 estimated API cost？ | 🔧 部分 | cache 機制已完成，但需要端到端 benchmark |
| **RQ3**: LRU、LFU、TTL 與 hybrid eviction 對 retrieval precision 和 memory pollution 有何影響？ | 🔧 部分 | eviction 已完成，需要加入 comparison benchmark |
| **RQ4**: Context compression ratio 與回答品質之間的轉折點在哪裡？ | ❌ | 需要 agent loop + LLM 回答品質評估 |

---

## 檔案結構

```
memlite/
  __init__.py              # 公開 API
  __main__.py              # python -m memlite
  models.py                # MemoryItem, enums, helpers
  manager.py               # MemoryManager (lifecycle rules)
  engine.py                # MemLiteEngine (facade: memory + vector + cache + eviction)
  cache.py                 # SemanticCache, CacheEntry, ScopeContext
  cli.py                   # memlite CLI (remember/recall/supersede/forget)
  retrieval_cli.py         # memlite-retrieval CLI (retrieve with trace)
  benchmark_cli.py         # memlite-benchmark CLI
  embeddings/
    base.py                # EmbeddingProvider protocol
    deterministic.py       # DeterministicHashEmbedding
  storage/
    base.py                # MemoryStore protocol
    sqlite.py              # SQLiteMemoryStore
  vector/
    base.py                # VectorIndex protocol
    sqlite.py              # SQLiteVectorIndex (exact search)
  policies/
    retrieval.py           # RetrievalService, scoring, config
    eviction.py            # TTL/LRU/LFU/Hybrid eviction
  evaluation/
    datasets.py            # BenchmarkDataset loader
    retrieval_benchmark.py # Single-strategy benchmark
    comparison_benchmark.py # Multi-strategy comparison
  providers/
    __init__.py            # LLMProvider, TokenCounter protocols
    fake.py                # FakeLLMProvider, FakeTokenCounter
tests/
  test_memory_manager.py
  test_retrieval.py
  test_retrieval_boundaries.py
  test_retrieval_benchmark.py
  test_comparison_benchmark.py
  test_dataset.py
  test_cache.py
  test_eviction.py
  test_providers.py
experiments/
  datasets/mvp.json        # 10 組 benchmark sequences
  results/                 # benchmark 輸出
docs/
  adr/                     # 6 篇架構決策紀錄
  PROJECT_PLAN.zh-TW.md
  FILE_GUIDE.zh-TW.md
  QUICKSTART.zh-TW.md
  BENCHMARK_RESULTS.zh-TW.md
  IMPLEMENTATION_HARDENING.zh-TW.md
```

---

## 更新紀錄

| 日期 | 更新內容 |
|------|---------|
| 2026-10-03 | 初始建立進度追蹤檔案 |
| 2026-10-03 | 完成 Semantic Cache、Eviction Policies、Provider Protocols、4 篇 ADR、README 擴充 |
