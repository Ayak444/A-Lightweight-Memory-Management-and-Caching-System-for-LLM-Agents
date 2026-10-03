# MemLite-Agent 完整專案計畫

> Owner: 陳格洋  
> Status: Active development  
> Positioning: 求職作品集 + 可重現的研究型 side project  
> Runtime baseline: Python 3.11+

## 1. 專案主張

MemLite-Agent 是放在 Agent 與 LLM 之間的輕量記憶中介層。它將長期狀態拆成 Working、Episodic、Semantic Memory 與 Semantic Cache，並讓每次取回、壓縮、淘汰與快取決策都留下可檢查的 trace。

核心問題：

> 在維持任務成功率的前提下，分層記憶與語意快取能否降低 context token、延遲與 API 成本，同時控制過期或錯誤記憶造成的污染？

## 2. 成功標準

MVP 必須同時滿足：

- 能跨程序保存並取回三種記憶。
- 能以向量候選加 hybrid score 取回相關記憶。
- 能解釋每個候選的分數、選取結果與拒絕原因。
- 能用 token budget 限制送入模型的記憶量。
- 能處理 TTL、去重、supersede 與 scope 隔離。
- 能以 exact/semantic cache 重用安全的回應。
- 能從固定資料集比較 baseline 與實驗組。
- 能匯出 token、latency、cost、precision、success 與 pollution 指標。
- 能透過 CLI 與 API 完成端到端 demo。
- 能在 Docker 中啟動並掛載持久化資料。

## 3. 功能需求

### FR-1 Memory lifecycle

- 建立、讀取、更新、軟刪除記憶。
- 支援 Working、Episodic、Semantic Memory。
- 保存 scope、來源、信心、重要性、TTL、版本與存取統計。
- 相同 scope、type 與內容的 active memory 去重。
- 新事實可以 supersede 舊事實並保留關係。

### FR-2 Retrieval

- Metadata filter 必須發生在最終選取之前。
- 以 embedding 找出 top-N candidates。
- 排除 expired、deleted 與 superseded memory。
- 以 similarity、recency、importance、confidence、frequency 與 pollution penalty 排序。
- 以 token budget 選出最終 context。
- 每個候選都回傳 score breakdown 與 rejection reason。

### FR-3 Semantic cache

- 支援 exact key 與 semantic candidate lookup。
- Cache scope 包含 query、system prompt、model、tool schema 與 context fingerprint。
- 支援 threshold、TTL、手動 invalidation 與 access stats。
- 區分 valid hit、miss 與 rejected hit。

### FR-4 Evaluation

- Dataset 必須包含 repetition、long-horizon、preference、update、conflict、irrelevant 與 scope isolation。
- 支援 full-history、recent-window、naive top-k、hierarchical、cache-enabled 實驗組。
- 每次 run 保存 config、環境、輸入、輸出、retrieval trace 與 metrics。
- 能產生 JSONL、CSV 與 Markdown summary。

### FR-5 Interfaces

- CLI：init、remember、recall、retrieve、supersede、forget、benchmark、report。
- API：memories、retrieval、cache、runs、trace、health。
- P1 UI：memory inspector、retrieval trace、benchmark comparison。

## 4. 非功能需求

- **可重現性**：離線 fake provider 的結果必須 deterministic。
- **可替換性**：核心邏輯不得直接綁定單一 LLM、embedding 或 vector backend。
- **可觀察性**：不可只回傳拼接後的 context；必須保留候選決策。
- **資料安全**：secret 不進 repository；log 預設不保存完整敏感 prompt。
- **一致性**：SQLite 是 source of truth；vector index 可以重建。
- **效能**：MVP benchmark 的 retrieval p95 目標小於 100 ms，不包含遠端 embedding。
- **測試性**：domain 與 policy 不需要網路即可測試。
- **相容性**：本機基準為 Python 3.11；部署使用 Linux container。

## 5. 架構

```text
CLI / FastAPI / Benchmark Runner
              |
              v
       MemLite Engine
       |      |      |
       |      |      +---------- Semantic Cache
       |      +----------------- Retrieval Policy
       +------------------------ Memory Manager
              |                         |
              v                         v
       Embedding Provider         SQLite Metadata
              |
              v
       Vector Index Adapter
       |                  |
       + Offline SQLite   + Chroma Persistent/Server
```

### 儲存原則

- SQLite metadata database 是主要事實來源。
- Offline SQLite vector index 是測試與 benchmark baseline，不宣稱是 production ANN database。
- Chroma `PersistentClient` 適合本機開發；正式部署改用 server-backed instance 或其他受管理向量服務。
- Vector index 每筆資料保存 `memory_id`、scope、type、model、dimension 與 normalized vector。

### 寫入一致性

MVP 先採可重試寫入：

1. 寫入 SQLite memory。
2. 計算 embedding。
3. Upsert vector index。
4. 若第 2 或 3 步失敗，memory 保留並記錄 index missing。
5. `reindex` 從 SQLite 重建向量。

Production 強化階段再加入 outbox，不在 MVP 先做分散式交易。

## 6. Repository 結構

```text
memlite/
  models.py                 # domain models
  manager.py                # memory lifecycle facade
  engine.py                 # memory + embedding + retrieval orchestration
  embeddings/               # provider protocols and adapters
  vector/                   # vector index protocols and adapters
  policies/                 # retrieval, scoring, compression, eviction
  cache/                    # exact and semantic cache
  storage/                  # SQLite metadata store
  evaluation/               # datasets, runner, metrics, report
  api/                      # FastAPI endpoints
experiments/
  datasets/                 # versioned benchmark inputs
  configs/                  # experiment matrix
  results/                  # generated artifacts, mostly gitignored
tests/
  unit/
  integration/
docs/
  adr/
```

目前 repository 尚未拆分 unit/integration 子目錄；測試數量增加後再移動，避免早期結構空洞。

## 7. 技術選型

| 項目 | MVP | 後續 |
| --- | --- | --- |
| Language | Python 3.11+ | 維持 |
| Domain model | dataclass + Protocol | API 邊界使用 Pydantic |
| Metadata | sqlite3 | SQLAlchemy/Alembic 視 migration 複雜度加入 |
| Offline vector baseline | SQLite + exact cosine scan | 保留做 deterministic baseline |
| Real vector backend | Chroma | 可替換 Qdrant/pgvector |
| API | FastAPI | OpenAPI + auth/rate limit |
| CLI | argparse | 可視需求換 Typer |
| Tests | unittest | pytest + coverage |
| Quality | compileall | Ruff + mypy + CI |
| Deployment | Docker | Zeabur persistent volume |

## 8. Benchmark 設計

第一版資料集至少 10 組 sequence，每組包含：

- 可被寫入的 memories。
- 一個或多個 query。
- expected relevant memory keys。
- expected answer facts。
- category 與污染/更新條件。

### 實驗組

| ID | 設定 |
| --- | --- |
| B0 | Full conversation history |
| B1 | Fixed recent token window |
| E1 | Lexical/deterministic vector top-k |
| E2 | Real embedding top-k |
| E3 | E2 + hybrid score + token budget |
| E4 | E3 + semantic cache |
| E5 | E4 + eviction/pollution handling |

### 主要指標

- Retrieval Precision@k、Recall@k、MRR。
- Context token 與 compression ratio。
- Cache valid hit rate 與 rejected-hit rate。
- End-to-end、retrieval、embedding、LLM latency p50/p95。
- Task success rate。
- Estimated API cost。
- Stale retrieval rate 與 pollution impact rate。

## 9. 里程碑與驗收

### M0 Foundation，已完成

- Git、package、README、ignore 與環境範例。
- MemoryItem、SQLite schema、MemoryManager、CLI。
- Persistence、TTL、dedupe、scope、supersede 測試。

驗收：關閉程式後仍能讀回記憶；5 個核心測試通過。

### M1 Explainable retrieval，進行中

- Deterministic embedding。
- Persistent offline vector index。
- Hybrid scoring 與 token budget。
- Retrieval trace 與 10 組 benchmark dataset。

驗收：相同資料與 query 每次產生相同排序；每個候選都有完整分數與選取理由。

### M2 Semantic cache

- Exact cache key、semantic lookup、scope fingerprint。
- TTL、invalidation、hit/miss/rejected-hit metrics。

驗收：同義 query 可命中；model/context version 改變時拒絕命中。

### M3 Provider 與 Agent loop

- Fake LLM、真實 LLM adapter、token counter。
- Prompt Builder 與最小 Agent loop。
- 成本與 latency trace。

驗收：同一 task sequence 可切換 fake/real provider。

### M4 Evaluation

- Baseline matrix、runner、metric aggregation、Markdown report。
- 失敗案例與 ablation study。

驗收：一條命令從乾淨資料庫產生完整結果資料夾。

### M5 API 與展示

- FastAPI、health、memory/retrieval/cache/run endpoints。
- Streamlit 或小型 web inspector。

驗收：使用者能看見某次回答使用的記憶與分數。

### M6 Deployment 與作品集

- Docker、persistent volume、secret、rate limit。
- GitHub Actions、demo、README、PPT 與真實圖表。

驗收：公開連結可用，另一台電腦能依 README 重現 benchmark。

## 10. 安全與隱私

- `.env`、API key、raw private prompts 不提交。
- API log 使用 memory id 與 hash；完整內容需明確開啟 debug 才保存。
- Scope 是所有查詢的必要條件，API 層不得接受無 scope 的 retrieval。
- Cache 不能跨 user/project scope 命中。
- Demo 設定輸入上限、rate limit、timeout 與成本 cap。
- 提供清除 scope 與重新建立 index 的管理命令。

## 11. 目前 Sprint

1. 完成 persistent offline vector index。
2. 完成 deterministic embedding 與 retrieval scoring。
3. 加入 token budget 與 trace。
4. 建立並驗證 10 組 benchmark dataset。
5. 為 retrieval persistence、scope、supersede、budget 寫測試。

下一個 Sprint 才開始 Semantic Cache，不同時開 FastAPI、UI 與部署三條線。

