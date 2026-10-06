# MemLite-Agent 開發進度追蹤

> **給 AI Agent 的指示**：這是本專案的進度總覽。開始任何工作前，請先讀完本文件，了解哪些已完成、哪些進行中、哪些尚未開始。完成任務後，請更新對應的狀態標記。
>
> **狀態標記**：✅ 完成 | 🔧 進行中 | ❌ 尚未開始 | ⏭️ 刻意跳過（非目標）

> **2026-10-03 驗證更新**：初稿的「全部完成」標記未附完整驗收證據。本輪依實際程式、68 個測試及離線實驗校正；研究問題的完成必須有品質／成本等實測，部署完成必須有可用的公開環境。詳見 [本輪研究紀錄](docs/RESEARCH_UPDATE_20261003.zh-TW.md)。

> **2026-10-05 更新**：可分發 skill、README／使用教學、TTL／來源修正與 Agent L2 整合完成；重要性保護 858 trace 與壓縮 108 trace 已量測，含負面結果。public 前的剩餘驗收見 [RELEASE_CHECKLIST](docs/RELEASE_CHECKLIST.zh-TW.md)。未 push、未發布或公開部署，不將本地封裝等同整個專案全部完成。

> **2026-10-06 修正與校正**：審查發現的 cache hit 抽取、L3 額外呼叫／用量與無效請求扣款已修正，138 tests／62 subtests 通過，lint／format／typing 通過，demo UTF-8 已修復。研究品質與展示缺口仍未驗收；下方 M2/M3/M4 校正為進行中。剩餘六項所需資料、預算與權限見 [修正與條件](docs/FIXES_AND_REQUIREMENTS_20261006.zh-TW.md)。

> **2026-10-06 GitHub 更新**：已依使用者授權 commit／push，補上一行 npx skill 安裝、安裝後檔案及操作驗收與 CI 步驟。pytest 139 tests／62 subtests 通過；提交 `19ac1ed` 的遠端 Python 3.11／3.12 CI、wheel 安裝、skill 安裝與 artifact 產出全數成功。GitHub metadata 顯示 repo 已為 public，本輪沒有更改 visibility；先前 private／未 push 敘述保留作歷史，不代表現況。實際 push 與遠端安裝結果記於文末。

---

## 專案定位

- **專案名稱**：MemLite-Agent: A Lightweight Hierarchical Memory and Semantic Cache System for LLM Agents
- **核心問題**：在不降低任務成功率的前提下，分層記憶、語意快取與 context 壓縮能否降低 LLM Agent 的 token、延遲與 API 成本？
- **定位**：求職作品集 + 可量化的研究原型
- **技術棧**：Python 3.11+ / SQLite / 本地向量搜尋 / FastAPI；本輪使用 Python 3.12.14
- **完整規格**：[PROJECT_GUIDE.md](PROJECT_GUIDE.md)

---

## Milestone 總覽

| Milestone | 名稱 | 狀態 | 說明 |
|-----------|------|------|------|
| M0 | 定義與骨架 | ✅ 完成 | repo、domain models、fake providers；Python 3.11／3.12 遠端 CI 已通過 |
| M1 | 可用的 Memory Manager | ✅ 完成 | SQLite schema、CRUD、向量檢索、trace |
| M2 | Compression 與 Semantic Cache | 🔧 進行中 | L2/L3 整合與用量／快取回歸已驗證；真實摘要品質與污染仍待驗收 |
| M3 | Evaluation | 🔧 進行中 | 離線 retrieval／cache／eviction／壓縮可重現；獨立資料與真實品質、費用尚未完成 |
| M4 | 作品集展示 | 🔧 進行中 | CLI 與 UTF-8 文字紀錄完成；完整 PPTX、GIF／截圖仍待完成 |
| M5 | 部署與發布 | 🔧 進行中 | skill ZIP 與 runtime wheel 離線安裝已驗證；Docker/公開部署需環境權限 |

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
| TTL-preserving supersede | ✅ | `memlite/manager.py`、`memlite/skill_cli.py` | 保留原絕對到期時間，不延長 TTL；過期記憶拒絕復活 |
| 修正來源參考 | ✅ | `memlite/engine.py`、`memlite/skill_cli.py` | 可附新 source / source_ref；不是自動真實性驗證或矛盾偵測 |

### 核心二：Semantic Cache

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| CacheEntry model | ✅ | `memlite/cache.py` | query_hash、scope_fingerprint、TTL |
| ScopeContext (scope fingerprint) | ✅ | `memlite/cache.py`、`memlite/agent/loop.py` | Agent 帶入 model／指令版本／實際 prompt context／tools version |
| Exact match lookup | ✅ | `memlite/cache.py` | 用 query_hash + scope_fingerprint |
| Semantic similarity lookup | ✅ | `memlite/cache.py` | 用 vector search + threshold |
| Scope fingerprint mismatch 拒絕 | ✅ | `memlite/cache.py` | rejected_hit event |
| TTL 過期 | ✅ | `memlite/cache.py` | |
| 手動 invalidation (single + scope) | ✅ | `memlite/cache.py`、`memlite/engine.py` | 記憶寫入／替代／刪除／淘汰亦失效同 scope 快取 |
| Hit/miss/rejected_hit 事件 log | ✅ | `memlite/cache.py` | cache_events table |
| CacheStats 統計 | ✅ | `memlite/cache.py` | total、active、hits、misses、rejected、hit_rate |
| 可調 similarity threshold | ✅ | `memlite/cache.py` | 建構參數 |

### 核心三：Evaluation 與 Observability

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| BenchmarkDataset loader + validator | ✅ | `memlite/evaluation/datasets.py` | 驗證 required categories |
| Retrieval benchmark | ✅ | `memlite/evaluation/retrieval_benchmark.py` | precision、recall、MRR、latency |
| Comparison benchmark (strategies) | ✅ | `memlite/evaluation/comparison_benchmark.py` | 多策略 + token budget + corpus latency |
| 長歷史／多必要事實／eviction 受控比較 | ✅ 首輪 | `memlite/evaluation/challenge_benchmark.py` | challenge v1.1.0；固定時間與存取狀態，17 策略、3 次重複、612 筆 trace |
| 可重用 Codex skill | ✅ | `docs/skills/memlite-agent/`、`memlite/skill_cli.py` | 記憶管理 + 接續研究；格式與 runtime 測試通過，使用說明見 docs/SKILL_USAGE.zh-TW.md |
| Skill 分發／封裝 | ✅ 本機 | `experiments/package_skill.py` | deterministic ZIP、manifest／SHA-256、MIT 授權與安裝說明；不包含資料庫或引擎，GitHub 遠端驗收待完成 |
| Runtime wheel 隔離安裝驗收 | ✅ 離線核心 | `experiments/smoke_installed_runtime.py` | build 成功，無依賴全新 venv 的 3 輪 lifecycle／scope／TTL 檢查通過；第三方 API 依賴另需驗收 |
| 重要性保護受控比較 | ✅ 首輪 | `memlite/evaluation/protection_benchmark.py` | 22 案例 × 13 策略 × 3 次，858 trace；36 改善、24 退步，無容量違規 |
| Agent 壓縮事實保留實驗 | ✅ 代理指標 | `memlite/evaluation/compression_benchmark.py` | 6 題 × 6 策略 × 3 次，108 實際 prompt trace；不是回答品質 |
| CSV / JSON 輸出 | ✅ | `memlite/evaluation/comparison_benchmark.py` | |
| Run / Event log 持久化到 SQLite | ✅ | `memlite/evaluation/run_log.py` | PROJECT_GUIDE 要求 runs、retrieval_events、metrics table |
| B0 baseline (full history) | ✅ | `memlite/evaluation/comparison_benchmark.py` | 原始寫入歷史，含被替代事實，繞過向量排名 |
| B1 baseline (recent window) | ✅ | `memlite/evaluation/comparison_benchmark.py` | 同 scope 最近十次寫入；另有超過視窗回歸測試 |
| summary.md report 產生器 | ✅ | `memlite/evaluation/summary.py` | |
| Dataset 擴充到 30+ 組 | ✅ | `experiments/datasets/mvp.json` | 包含 31 組 sequences |
| environment.json (git commit, versions) | ✅ | `memlite/evaluation/environment.py` | |

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
| 過期／無效 hit 候選補足 | ✅ | `memlite/policies/retrieval.py` | 有效候選不足時擴大前綴，保留掃描上限與 scan trace；不刪除記憶 |
| 候選補足配對驗證 | ✅ | `experiments/run_refill_comparison.py` | 固定 12 案例 × 17 策略 × 兩條件 × 3 次；控制組重現歷史、48 trace 改善、無退步 |

### Eviction Policies

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| EvictionPolicy protocol | ✅ | `memlite/policies/eviction.py` | |
| TTLEviction | ✅ | `memlite/policies/eviction.py` | 用 list_expired 查過期條目 |
| LRUEviction | ✅ | `memlite/policies/eviction.py` | 依 last_accessed_at 排序 |
| LFUEviction | ✅ | `memlite/policies/eviction.py` | 依 access_count 排序 |
| HybridEviction (TTL + LRU/LFU) | ✅ | `memlite/policies/eviction.py` | |
| 有上限重要記憶保護 | ✅ opt-in | `memlite/policies/eviction.py` | 門檻 0.8/0.8、預留 1 名額的固定研究；錯誤高評分也會被保留，不改預設 |
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
| OpenAI adapter | 🔧 | `memlite/providers/openai_provider.py` | SDK adapter 與型別檢查存在；未付費連線驗證或品質評估 |
| 真實 embedding provider | 🔧 | `memlite/embeddings/openai_embedding.py` | OpenAI adapter 存在；維度與真實檢索效果待驗證 |

### Agent Loop

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| agent/loop.py | ✅ | `memlite/agent/loop.py` | 最小 Agent 執行流程 |
| agent/prompt_builder.py | ✅ | `memlite/agent/prompt_builder.py` | 記憶 + 指令 + task → prompt |
| Memory extraction (LLM 結果寫回記憶) | 🔧 | `memlite/agent/loop.py` | opt-in 關鍵字抽取與 cache hit 副作用已測試；抽取句子不代表真實事實，污染／矛盾待驗證 |
| 端到端 task sequence demo | ✅ | `memlite/demo.py` | PROJECT_GUIDE §2.2 的 6 步情境 |

### Compression

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| Token-budget selection (L1) | ✅ | `memlite/policies/retrieval.py` | 依 score 選入直到超預算 |
| Extractive compression (L2) | ✅ | `memlite/policies/compression.py` | 只保留與 query 最相關的句子 |
| Agent L2 整合 | ✅ opt-in | `memlite/agent/prompt_builder.py` | memory_token_budget；只壓縮選入的記憶，不改 SQLite 原文，cache 指紋使用實際 context |
| Abstractive summary (L3) | ✅ 實作／🔧 品質 | `memlite/policies/compression.py`、`memlite/agent/prompt_builder.py` | 缺 provider 拒絕、選模、成功用量與 cache miss 呼叫測試完成；真實品質尚待評估 |
| 獨立 compression.py 模組 | ✅ | `memlite/policies/compression.py` | |

### API 與 CLI

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| CLI: init / remember / recall / supersede / forget | ✅ | `memlite/cli.py` | |
| CLI: retrieve (with score trace) | ✅ | `memlite/retrieval_cli.py` | |
| CLI: reindex | ✅ | `memlite/retrieval_cli.py` | |
| CLI: benchmark | ✅ | `memlite/benchmark_cli.py` | |
| FastAPI: /v1/memories CRUD | ✅ | `memlite/api/main.py` | |
| FastAPI: /v1/retrieval/query | ✅ | `memlite/api/main.py` | |
| FastAPI: /v1/cache | ✅ | `memlite/api/main.py` | |
| FastAPI: /health | ✅ | `memlite/api/main.py` | |

### 部署

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| Dockerfile | ✅ | `Dockerfile` | |
| docker-compose.yml | ✅ | `docker-compose.yml` | |
| Health check endpoint | ✅ | `memlite/api/main.py` | |
| Rate limit / input quota | ✅ 示範 | `memlite/api/main.py` | 失敗返還配額；process-local UTF-8 token 估計，不是登入／scope 授權或實際成本上限 |
| 真實費用 budget cap | ❌ | Agent/provider 評測路徑 | 尚需模型用量、價格版本、持久化記錄與超額拒絕／重試規則 |
| Zeabur / Render 部署 | ❌ | `Dockerfile` | 只有 Docker 設定，沒有公開部署驗收證據 |

### 文件

| 項目 | 狀態 | 檔案 | 備註 |
|------|------|------|------|
| PROJECT_GUIDE.md | ✅ | `PROJECT_GUIDE.md` | 完整規格 |
| README.md | ✅ | `README.md` | 含架構圖、操作範例、限制與最新研究入口 |
| ADR 0001: SQLite as source of truth | ✅ | `docs/adr/0001-*.md` | |
| ADR 0002: Provider-agnostic core | ✅ | `docs/adr/0002-*.md` | |
| ADR 0003: Separate metadata and vector | ✅ | `docs/adr/0003-*.md` | |
| ADR 0004: Cache scope and invalidation | ✅ | `docs/adr/0004-*.md` | |
| ADR 0005: Memory versioning and supersession | ✅ | `docs/adr/0005-*.md` | |
| ADR 0006: Evaluation baselines | ✅ | `docs/adr/0006-*.md` | |
| ADR 0007: Metadata-aware candidate refill | ✅ | `docs/adr/0007-metadata-aware-candidate-refill.md` | 有效候選、穩定前綴、上限與額外索引掃描成本 |
| ADR 0008: Bounded importance protection | ✅ | `docs/adr/0008-bounded-importance-protection.md` | 有限容量與不可靠評分的污染限制 |
| QUICKSTART 文件 | ✅ | `docs/QUICKSTART.zh-TW.md` | |
| Demo 文字紀錄 | ✅ | `docs/demo_output.txt` | 程式直接匯出 UTF-8，0 替代字元；不等於 GIF／截圖 |
| Demo GIF／截圖與完整 PPTX | ❌ | 展示資料夾 | 目前只有 outline 與單張 slide；未以文字檔替代視覺驗收 |
| 失敗案例分析 | ✅ | `docs/BENCHMARK_RESULTS.zh-TW.md` | |
| 代表性實驗表格 | ✅ | `docs/RESEARCH_UPDATE_20261003.zh-TW.md` | 31 題 B0/B1 與 fake-provider cache 比較；舊報告保留歷史數據 |
| 候選補足修正與配對驗證紀錄 | ✅ | `docs/RETRIEVAL_REFILL_20261004.zh-TW.md` | 1,224 trace、歷史控制一致性、31 題回歸及上限限制 |
| 重要性保護研究報告 | ✅ | `docs/IMPORTANCE_PROTECTION_20261005.zh-TW.md` | 固定規則、858 trace、252 歷史控制一致、改善與退步 |
| 壓縮與修正研究報告 | ✅ | `docs/COMPRESSION_AND_CORRECTION_20261005.zh-TW.md` | TTL 不延長、修正來源、L2 context 與 108 trace 事實保留曲線 |
| 安裝與操作教學 | ✅ | `docs/SKILL_USAGE.zh-TW.md`、`docs/SKILL_INSTALL.zh-TW.md` | GitHub／ZIP、跨平台、五分鐘完整 CRUD 教學與排錯 |
| Public 前驗收清單 | ✅ 文件 | `docs/RELEASE_CHECKLIST.zh-TW.md` | checklist 已建立，不代表待辦已完成 |

### 測試

| 項目 | 狀態 | 檔案 | 測試數 |
|------|------|------|--------|
| Memory Manager tests | ✅ | `tests/test_memory_manager.py` | 5 |
| Retrieval tests | ✅ | `tests/test_retrieval.py` | 6 |
| Retrieval boundary tests | ✅ | `tests/test_retrieval_boundaries.py` | 4 |
| Dataset validation test | ✅ | `tests/test_dataset.py` | 1 |
| Retrieval benchmark test | ✅ | `tests/test_retrieval_benchmark.py` | 1 |
| Comparison benchmark tests | ✅ | `tests/test_comparison_benchmark.py` | 2 |
| Semantic cache tests | ✅ | `tests/test_cache.py` | 12 |
| Eviction policy tests | ✅ | `tests/test_eviction.py` | 9 |
| Provider tests | ✅ | `tests/test_providers.py` | 7 |
| Agent loop tests | ✅ | `tests/test_agent_loop.py` | 9 |
| Cache boundary tests | ✅ | `tests/test_cache_boundaries.py` | 3 |
| Compression tests | ✅ | `tests/test_compression.py` | 5 |
| API tests | ✅ | `tests/test_api.py` | 9 |
| Agent cache benchmark test | ✅ | `tests/test_agent_benchmark.py` | 1 |
| Challenge benchmark tests | ✅ | `tests/test_challenge_benchmark.py` | 6 |
| Skill bridge tests | ✅ | `tests/test_skill_cli.py` | 5 |
| Retrieval refill tests | ✅ | `tests/test_retrieval_refill.py` | 6 |
| Paired refill comparison tests | ✅ | `tests/test_refill_comparison.py` | 2 |
| Protected eviction tests | ✅ | `tests/test_protected_eviction.py` | 9 |
| Protection comparison tests | ✅ | `tests/test_protection_benchmark.py` | 4 |
| Skill distribution tests | ✅ | `tests/test_skill_distribution.py` | 7 |
| TTL correction tests | ✅ | `tests/test_ttl_correction.py` | 6 |
| Agent compression tests | ✅ | `tests/test_agent_compression.py` | 6 |
| Compression benchmark tests | ✅ | `tests/test_compression_benchmark.py` | 2 |
| Prompt builder strategy tests | ✅ | `tests/test_prompt_builder.py` | 3 |
| Agent accounting／cache 副作用 tests | ✅ | `tests/test_agent_accounting.py` | 8 |
| Demo UTF-8 export test | ✅ | `tests/test_demo_output.py` | 1 |
| **合計** | | | **139（另有 62 個 subtests）** |

---

## 研究問題對應

| 研究問題 | 可回答程度 | 缺什麼 |
|---------|-----------|--------|
| **RQ1**: Hierarchical memory 能否在維持 task success rate 的情況下降低 token usage？ | 🔧 初步 | 長歷史與多必要事實的 synthetic 檢索／token 已量測；真實回答品質與獨立 held-out data 待驗證 |
| **RQ2**: Semantic cache 能降低多少 latency 與 estimated API cost？ | 🔧 初步 | fake-provider exact repeats 30→6 calls；真實語意改寫、網路延遲與成本待量測 |
| **RQ3**: LRU、LFU、TTL 與 hybrid eviction 對 retrieval precision 和 memory pollution 有何影響？ | 🔧 首輪完成 | 保護能留住冷門重要記憶，也誤保護錯誤事實；來源修正已有，矛盾偵測與獨立資料仍待驗證 |
| **RQ4**: Context compression ratio 與回答品質之間的轉折點在哪裡？ | 🔧 代理指標首輪 | L2/L3 已接入 Agent，六題預算／事實保留實驗完成；真實回答品質依賴第三方 API |

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
  skill_cli.py             # scope-explicit JSON bridge
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
    protection_benchmark.py # 固定容量、重要性評分可靠度與污染
    compression_benchmark.py # 實際 Agent context 的必要事實保留
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
  datasets/mvp.json        # v2.0.0，31 組 benchmark sequences
  datasets/protection.json # protection-1.0.0，22 個固定壓力案例
  datasets/compression.json # compression-1.0.0，6 個必要事實案例
  package_skill.py         # 可重現下載包，不包含 runtime／資料庫
  results/                 # benchmark 輸出
docs/
  adr/                     # 8 篇架構決策紀錄
  skills/memlite-agent/    # 可安裝的記憶／研究雙模式 skill
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
| 2026-10-03 | 完成所有剩餘任務：B0/B1 baseline、FastAPI endpoints 加上 rate limit、各種策略實作與報表更新 |
| 2026-10-03 | 核對上列初稿：46 tests 中 3 失敗，Agent/API 欄位與 cache context 尚未接好；完成修正後 68 tests 通過，新增可重現實驗並校正研究／部署狀態 |
| 2026-10-03 | 接續長歷史／多必要事實與 eviction 首輪研究；challenge v1.1.0、612 筆 trace；新增記憶與研究雙模式 skill，79 tests 與 18 subtests 通過 |
| 2026-10-04 | 完成有上限的候選補足與 scan trace，配對驗證 1,224 trace；48 trace 改善、無退步，31 題品質與 token 指標不變；87 tests、29 subtests 通過 |
| 2026-10-05 | 完成重要性保護、22 題固定比較與 858 trace，36 改善／24 退步、歷史控制 252 筆一致；維持 opt-in |
| 2026-10-05 | 整理 GitHub skill 下載包、MIT LICENSE、README、跨平台教學與 public 前驗收；未 push 或改 visibility |
| 2026-10-05 | 修正 supersede TTL 與來源，L2 接入 Agent；108 compression trace 顯示預算 32/64 仍丟失必要長句；120 tests、62 subtests 驗證 |
| 2026-10-06 | 完成度審查重現 cache hit 抽取、L3 用量與錯誤配額問題，125 tests 仍通過但 lint／format 失敗；完整審查保留為歷史紀錄 |
| 2026-10-06 | 修正上述問題與 builder 配置、清理格式、UTF-8 demo；138 tests／62 subtests、unittest、Ruff、mypy 通過；本機 skill 先備份後同步 |

## 本輪成果與接續工作

- 驗收紀錄：[RESEARCH_UPDATE_20261003.zh-TW.md](docs/RESEARCH_UPDATE_20261003.zh-TW.md)。
- 原始資料：`experiments/results/research-20261003/`，含 comparison.json、agent_cache_comparison.json、environment.json、runs.db、CSV 與 summary.md；依既有 ignore 規則保留本機。
- Hybrid Top-1：31 題通過 29 題（93.55%）；B0：22 題（70.97%）。它們是 retrieval pass，未宣稱 LLM task success。
- Fake-provider repeat test：30 tasks，24 cache hits，provider calls 30→6；本機快取較慢，真實 API latency benefit 尚未量測。
- 本輪完成：新增超過十筆的長歷史、多必要事實與污染案例，development/evaluation 各 6 題但共用模板，不宣稱為真正獨立 held-out 資料。受控 eviction 結果見 [CHALLENGE_RESULTS_20261003.zh-TW.md](docs/CHALLENGE_RESULTS_20261003.zh-TW.md)。
- 正式原始資料：`experiments/results/research-challenge-20261003-v2/`；固定資料 `experiments/datasets/challenge.json`、runner 與文字報告可版控，JSON/CSV 本機保留並可重現。
- Skill 使用方式：[SKILL_USAGE.zh-TW.md](docs/SKILL_USAGE.zh-TW.md)，包含 scope 記憶 CRUD／檢索與接續研究兩種模式；已安裝至本機 Codex skills 並驗證副本一致，尚未做獨立 Agent 行為評估。
- 2026-10-04 完成候選補足修正與驗證：[RETRIEVAL_REFILL_20261004.zh-TW.md](docs/RETRIEVAL_REFILL_20261004.zh-TW.md)。正式配對資料 `experiments/results/refill-20261004-verified/`；原本 31 題回歸資料 `experiments/results/retrieval-regression-20261004/`。
- 修正後 evaluation top-3 通過率 50%→66.67%，改善僅來自過期候選案例；控制組重現前輪，沒有其他選取／淘汰差異或通過題退步。這不是 LLM task success 或真正 held-out validation。
- 2026-10-05 重要性保護完成：[IMPORTANCE_PROTECTION_20261005.zh-TW.md](docs/IMPORTANCE_PROTECTION_20261005.zh-TW.md)；正式資料 `experiments/results/importance-protection-20261005-verified/`，858 trace、252 歷史控制一致，36 改善／24 退步與 36 筆誤保護均記錄。
- 2026-10-05 TTL／來源修正與 L2 整合完成：[COMPRESSION_AND_CORRECTION_20261005.zh-TW.md](docs/COMPRESSION_AND_CORRECTION_20261005.zh-TW.md)；正式資料 `experiments/results/compression-20261005-verified/`，108 trace、0 budget 違規、0 原文改寫。budget 32 / 64 只有 5/6 題保留全部必要事實，未完成真實回答品質驗收。
- Skill 本機可分發，原始碼、JSON 範例與完整教學已補齊；來源 skill 已更新，個人安裝副本不自動同步。GitHub CI 封裝 artifact 定義已加入，但未遠端執行或發布下載。
- 本機下載包：`dist/memlite-agent-skill-0.1.0-20261005.zip`，11 個檔案；SHA-256 `aa84da335aaedca25085c1cf62861570fddf1b9a8f0ed0234ae1b51803664630`。安裝說明位於包內 INSTALL.md；ZIP 與 runtime wheel 依規則忽略、不將 build／venv 加入 Git。
- 完整驗證：pytest 120 tests／62 subtests 通過；unittest 120 tests 通過；Ruff check／116 個檔案 formatting、strict mypy 47 個 source files、skill quick_validate 與 Git diff whitespace check 通過。
- **下一個研究切片**：先凍結獨立任務與人工品質 rubric，加入明確來源／版本的矛盾案例，再比較 L1/L2；不依新 evaluation labels 調參。L3 與真實 provider 品質／usage／成本需要模型、費用上限及資料傳送授權。
- **安裝驗收**：研究 venv 缺 setuptools；改用內建 Python 的 setuptools 84.0.0／wheel 0.48.0，在無網路下載下完成 wheel build，並裝到全新 venv，以隔離模式執行 3 輪 lifecycle／scope／TTL。這只驗證離線核心，沒有將第三方 API 依賴的安裝說成已完成。
- **外部驗收條件**：本機沒有 docker，容器尚未 build／執行；遠端 provider 需費用與資料傳送授權，GitHub CI／Release 需 private push 後驗收。無論何種限制，均不能勾選部署完成。
- GitHub private CI、乾淨安裝、Git 歷史／素材檢查、Release、UI／GIF／完整簡報與公開部署的完成條件集中於 [RELEASE_CHECKLIST.zh-TW.md](docs/RELEASE_CHECKLIST.zh-TW.md)。轉 public 由使用者決定，不是 skill 預設動作。

## 2026-10-06 最新驗收

- 修正內容與完成剩餘六項的實際條件：[FIXES_AND_REQUIREMENTS_20261006.zh-TW.md](docs/FIXES_AND_REQUIREMENTS_20261006.zh-TW.md)。先前審查為修正前快照，不把已排除的錯誤當成仍存在。
- pytest 138／62 subtests 通過；unittest 138 通過；Ruff check、121 檔 format、strict mypy 47 source files 通過。沙箱會限制 SQLite／本機 socketpair，完整 API 測試經工具授權於可用環境執行；沒有付費 API。
- UTF-8 demo 可重現匯出，0 替代字元。138 tests 中含新增 13 個回歸／匯出測試；原有新加的 PromptBuilder／抽取／配額測試保留。
- 新 wheel 位於 `dist/runtime-fixed-20261006/memlite_agent-0.1.0-py3-none-any.whl`，新隔離環境驗證基本 lifecycle、TTL／scope，以及 L3 加總、零呼叫 cache hit 與授權抽取通過；不靠 editable source。第三方 API 依賴與遠端驗收仍未宣稱完成。
- 本機 `.codex/skills/memlite-agent` 舊版備份在 `dist/skill-backup-20261006-before-fixes/`；八個來源檔逐一核對相同，metadata policy 與其他技能未改。
- L2 固定六題／108 trace 重新驗證於 `experiments/results/compression-fixed-20261006/`，六個結果列與前輪完全相同；這不是 L3 真實回答品質證據。
- 最新 skill ZIP：`dist/memlite-agent-skill-0.1.0-fixed-20261006.zip`，11 檔；SHA-256 `6683b4f713ff3785a1c2a7ff2e5709ce9035c4a4fbf25e6c1a45b90b4aa7ebe2`。舊包保留歷史，不把舊 checksum 當成新版 checksum。
- repo 尚未 commit／push／Release 或改 visibility。正式版本 tag、Git 歷史與素材檢查、乾淨 GitHub 安裝及 Docker 仍需接續驗收。

## 2026-10-06 一行安裝與 GitHub 提交

- README、完整教學及 ZIP 說明加入已驗證版本 `skills@1.7.0` 的一行安裝；直接指向 `docs/skills/memlite-agent`，指定 Codex/global/copy。不把 skill 安裝誤稱為 Python runtime 安裝，不默默下載引擎或呼叫 API。
- 在 `dist/npx-install-smoke-20261006/` 用官方 CLI 實際安裝本地 skill 副本；八檔 byte match，從其他工作目錄 remember／retrieve／list 成功，零遠端 API 呼叫，未修改既有全域 skill。
- 新增 `experiments/smoke_installed_skill.py`、一個成功／破壞檔案驗收測試，CI 加入 Node 22、同版本 CLI 安裝及 smoke；Ruff 排除生成的實驗輸出與建置產物。
- pytest 139 tests／62 subtests 通過；Ruff check／76 檔 format、strict mypy 48 source files 與安裝 smoke 通過。既有 staged 版本含舊格式，提交時採最新已驗證內容，不退回舊版。
- 排除本機 `.agents/`、`.env.*`（保留 `.env.example`）、資料庫與 dist；工作目錄 133 個候選檔案及原有一個 commit 的常見 credential pattern 掃描無命中。這不是完整個資／授權稽核：Git 歷史原已包含 `.codex/config.toml` 的本機路徑；本輪不更改既有設定或宣稱已完成公開前全面審查。
- 遠端 main 與本機 HEAD 原本一致；GitHub metadata 顯示 public，沒有修改 visibility、建立 Release 或部署 API。push 與遠端安裝驗收將在完成後追加；研究品質、Docker 與完整簡報尚未完成。
- 安裝教學更新後的新 ZIP：`dist/memlite-agent-skill-0.1.0-install-20261006.zip`，11 檔，SHA-256 `b656dbb4e5a49db2e4c56bd26ebd0a305d4a2acdfdbbfcc9239b0035260a92e8`。ZIP 在本機保留，不自動建立 Release 或提交建置產物。

### 遠端驗收結果

- 已提交並 push `19ac1ed7487f06d030e308635926cb8bac205c72` 至 origin/main，`git ls-remote` 與本機 SHA 一致；沒有 force push、改 visibility、建立 Release。
- 用停用 Git credential helper 的全新 clone 下載公開 repo 到 `dist/github-clean-20261006/`；再以 README 的 GitHub tree URL、`skills@1.7.0` 安裝到 `dist/github-skill-install-20261006/`。為避免覆蓋既有全域 skill，驗收只將目的地由 global 改成 project-level；沒有宣稱在作者全域目錄重裝或完成獨立 Agent 行為評估。
- 對遠端下載的副本驗證八個檔案 byte match、跨目錄 remember／retrieve／list 全數成功；scope／UTF-8 教學可執行，沒有呼叫模型 API。完整教學的修正／忘記流程已有測試覆蓋，但另一台實體機器的人工教學驗收仍未做。
- [GitHub Actions run 37480162794](https://github.com/Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents/actions/runs/37480162794) completed/success；Python 3.11／3.12 各完成依賴安裝、lint／format／typing、完整測試、wheel build、全新 venv 的隔離 wheel smoke、skill ZIP 封裝、官方 CLI 安裝及操作 smoke。
- 遠端已產生 `memlite-agent-skill-python-3.11`、`memlite-agent-skill-python-3.12` 兩個未過期 artifacts，各 11,440 bytes（GitHub artifact 外層包）。這不是 GitHub Release，也不將 artifact 外層 digest 當成內容 ZIP 的 SHA-256；保存期限與下載登入規則由 GitHub 決定。
- 安裝驗收測試再次 7/7 通過，skill-creator 格式驗證通過。原始提交後，本段文件另作驗收紀錄 commit；上述 CI 成功證據明確對應 `19ac1ed`，不預先宣稱後續文件提交的 CI 結果。
