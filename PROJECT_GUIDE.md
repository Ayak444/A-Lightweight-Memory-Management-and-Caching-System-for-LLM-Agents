# MemLite-Agent 專案執行指南

> **專案名稱**：MemLite-Agent: A Lightweight Hierarchical Memory and Semantic Cache System for LLM Agents  
> **一句話定位**：為 LLM Agent 提供可查看、可評估、可替換策略的分層記憶與語意快取中介層。  
> **主要導向**：求職作品集，同時保留足夠嚴謹的實驗設計，讓成果可整理成技術文章或專題報告。

---

## 0. 先知道我們要完成什麼

這個專案不以「做出最聰明的 Agent」為目標，而是回答一個更具體、也更容易量化的問題：

> 在不明顯降低任務成功率的前提下，輕量化的分層記憶、語意快取與 context 壓縮，能否降低 LLM Agent 的 token、延遲與 API 成本？

第一個可展示版本完成時，使用者應該能夠：

1. 送出一組連續、彼此相關的任務給 Agent。
2. 查看 Agent 寫入與取用了哪些 Working、Episodic、Semantic Memory。
3. 看見 Semantic Cache 是否命中，以及為什麼命中。
4. 切換 retrieval、compression、eviction 策略並重新執行實驗。
5. 比較「無記憶」與「MemLite」在 token、latency、cost、task success 等指標上的差異。

### 完成的定義（Definition of Done）

- 有一個可以從頭跑完的 demo，而不是只有獨立模組。
- 有至少一個 baseline 可比較，例如 `no-memory`。
- 每一次執行都會留下可重現的設定、輸入、輸出與 metrics。
- README 能讓陌生人在 10 分鐘內啟動專案。
- 有公開程式碼、線上展示或錄製好的完整 demo。
- 結果包含失敗案例，不只展示最好看的數字。

---

## 1. 明確的目標與主題

### 1.1 動機

LLM Agent 在長時間或重複任務中常遇到以下問題：

- 對話歷史持續增長，造成 input token、延遲與費用上升。
- 每次都重新回答相似問題，沒有重用已完成工作的機制。
- 單純使用向量相似度容易抓到看似相關、實際無用的記憶。
- 錯誤、過期或互相衝突的記憶會污染後續推理。
- 多數框架把記憶藏在內部，難以查看某次回答究竟用了什麼。

MemLite-Agent 的價值在於把「記憶」當成一個可以被觀察、修改、比較與評估的外部系統，而不是無限制保留 conversation history。

### 1.2 專案定位

本專案採用「作品集優先，研究方法加值」的定位。

| 面向 | 決策 | 原因 |
| --- | --- | --- |
| 求職作品集 | 主要定位 | 可展示後端設計、資料庫、LLM integration、測試、部署與效能分析 |
| 學習新技術 | 次要定位 | 練習 embeddings、vector search、cache policy、evaluation |
| 研究原型 | 次要定位 | 用 ablation study 與量化指標驗證各策略 |
| 純娛樂功能 | 暫不優先 | 不影響核心問題的 UI 動畫、多人協作、複雜 Agent 編排先不做 |

### 1.3 目標使用者

- 想降低 Agent token 與重複呼叫成本的開發者。
- 想研究 memory policy，但不想先採用大型 Agent framework 的學生或工程師。
- 想用透明介面檢查 memory retrieval 與污染問題的系統設計者。

### 1.4 核心研究問題

- **RQ1**：Hierarchical memory 能否在維持 task success rate 的情況下降低 token usage？
- **RQ2**：Semantic cache 能降低多少 latency 與 estimated API cost？
- **RQ3**：LRU、LFU、TTL 與 hybrid eviction 對 retrieval precision 和 memory pollution 有何影響？
- **RQ4**：Context compression ratio 與回答品質之間的轉折點在哪裡？

### 1.5 非目標

第一版明確不做：

- Graph Memory 或 Knowledge Graph。
- 多 Agent orchestration。
- 自行訓練 embedding model 或 LLM。
- 複雜權限、多租戶、計費系統。
- 支援所有 LLM provider。
- 大規模分散式 cache。
- 追求 production 級高可用性。

這些不是永遠不做，而是不能阻擋 MVP 完成。

---

## 2. 核心功能與範圍控制（MVP）

### 2.1 MVP 只做三件事

#### 核心一：Memory lifecycle

系統可以將資訊寫入不同記憶層、取回相關記憶、壓縮成有限 context，並在超過限制時淘汰資料。

最小功能：

- Working Memory：保存當前 task/session 的短期狀態。
- Episodic Memory：保存完成任務的事件摘要、輸入與結果。
- Semantic Memory：保存從事件中萃取的穩定事實、偏好或規則。
- Retrieval：以 metadata filter + vector similarity 找回候選記憶。
- Compression：在 token budget 內選取或摘要內容。
- Eviction：支援 TTL 與 LRU；LFU、hybrid 可放在下一階段。

#### 核心二：Semantic cache

相同或語意近似的請求可以直接重用既有結果，但必須納入足以判斷答案是否仍有效的 context。

最小功能：

- Exact cache key。
- Semantic similarity lookup。
- 可調整 similarity threshold。
- TTL 與手動 invalidation。
- 記錄 hit、miss、rejected hit 與節省的 token/latency/cost。

快取鍵不可只包含 user query。至少需要納入：

```text
cache_scope = hash(
  normalized_query,
  system_prompt_version,
  model_id,
  tool_schema_version,
  relevant_context_fingerprint
)
```

這可以避免「問題文字很像，但模型、工具或背景資料已經不同」時錯誤重用答案。

#### 核心三：Evaluation 與 observability

每次實驗都要回答：用了哪些記憶、為什麼被選中、花了多少資源、結果是否正確。

最小功能：

- 統一的 run/event log。
- 每個 retrieval result 的分數與來源。
- baseline 與 MemLite 的比較報表。
- 匯出 JSON/CSV，方便畫圖或寫報告。
- 一個簡單 dashboard 或 CLI summary。

### 2.2 MVP 使用情境

建議先做「個人研究助理」情境，因為它容易建立連續且可判分的任務：

1. 使用者先提供專案限制、偏好與背景資料。
2. Agent 完成一系列相關的分析或問答任務。
3. 後續問題會重用某些資訊，也會故意加入過期或衝突資訊。
4. 比較 Agent 在不同 memory policy 下的成本與正確率。

範例任務序列：

```text
Task 1: 記住專案只能使用 MIT/Apache-2.0 授權套件。
Task 2: 根據提供的文件比較三個向量資料庫。
Task 3: 延續前次限制，推薦其中一個方案。
Task 4: 更新限制：部署環境不允許常駐外部資料庫。
Task 5: 再次詢問推薦，觀察過期記憶是否被正確取代。
Task 6: 用不同措辭重問 Task 3，測試 semantic cache。
```

### 2.3 功能優先級

| 優先級 | 內容 | 是否阻擋 MVP |
| --- | --- | --- |
| P0 | SQLite schema、memory CRUD、run log | 是 |
| P0 | Vector retrieval、top-k、metadata filter | 是 |
| P0 | Semantic cache、TTL、threshold | 是 |
| P0 | Token budget、metrics、baseline | 是 |
| P1 | LRU/LFU/hybrid eviction 比較 | 否 |
| P1 | 記憶查看與手動刪改介面 | 否，但很適合作品集 |
| P1 | Retrieval trace dashboard | 否，但很適合作品集 |
| P2 | Graph Memory、多 Agent、使用者帳號 | 否 |

### 2.4 範圍變更規則

新增功能前必須回答：

1. 它是否直接幫助回答四個研究問題之一？
2. 沒有它，MVP 是否無法完成端到端 demo？
3. 它是否能在兩個工作日內完成並測試？

三題都是否定時，先放進 `BACKLOG.md`，不要加入目前 sprint。Side project 常卡住的原因之一就是缺少清楚結構、期限與取捨，因此每個 milestone 都必須有可驗收產物，而不是只有「繼續研究」。

---

## 3. 技術與架構選型

### 3.1 建議技術棧

| 層級 | MVP 選擇 | 用途 |
| --- | --- | --- |
| 語言 | Python 3.12 | LLM、embedding、evaluation 生態完整 |
| API | FastAPI + Pydantic | 型別清楚、自動產生 OpenAPI、方便部署 |
| CLI | Typer | 快速執行 demo 與 benchmark |
| Metadata DB | SQLite + SQLAlchemy/Alembic | 輕量、可檢查、可 migration |
| Vector DB | Chroma persistent mode | 本機持久化、上手成本低 |
| LLM adapter | 自訂小型 protocol/interface | 避免核心邏輯綁死單一供應商 |
| Token counting | provider tokenizer 或 tiktoken adapter | 計算 context 與節省 token |
| 測試 | pytest | unit、integration、evaluation smoke test |
| 品質工具 | Ruff + mypy | formatting、lint、基本型別檢查 |
| Demo UI | Streamlit（P1） | 快速展示 memory trace 與 metrics |
| 容器 | Docker Compose | 固定執行環境與部署流程 |

> 若 Chroma 在部署環境的持久化不穩定，第二選擇是 Qdrant；但 MVP 不應同時維護兩個 vector backend。

### 3.2 系統架構

```text
User / Benchmark
       |
       v
   Agent Loop
       |
       v
+-----------------------+
|    Memory Manager     |
|-----------------------|
| Working Memory        |
| Episodic Memory       |
| Semantic Memory       |
| Semantic Cache        |
| Policy Engine         |
+-----------------------+
   |        |         |
   |        |         +--> Metrics / Trace Store
   |        +------------> Vector DB
   +---------------------> SQLite
       |
       v
Retrieval -> Dedupe -> Rank -> Compress
       |
       v
  Prompt Builder
       |
       v
      LLM
       |
       +--> Response / Tool result
       |
       +--> Memory extraction and write-back
```

### 3.3 模組責任

```text
memlite/
  agent/
    loop.py                 # Agent 執行流程；保持薄且可替換
    prompt_builder.py       # 將指令、記憶與 task 組成有限 context
  memory/
    manager.py              # 對外 facade，協調各記憶層與 policy
    models.py               # MemoryItem、CacheEntry、RetrievalResult
    working.py              # session scoped memory
    episodic.py             # event/task history
    semantic.py             # stable facts/preferences/rules
    cache.py                # exact + semantic cache
  policies/
    retrieval.py            # filter、candidate generation、ranking
    compression.py          # token budget、extractive/summary strategy
    eviction.py             # TTL、LRU、LFU、hybrid
    scoring.py              # 統一 scoring contract
  storage/
    sqlite.py               # metadata、run、metric repository
    vector.py               # Chroma adapter
  providers/
    base.py                 # LLM/embedding/tokenizer protocols
    openai.py               # 第一個真實 provider adapter
    fake.py                 # 測試與離線 benchmark
  evaluation/
    runner.py               # 執行 experiment matrix
    metrics.py              # 指標定義與計算
    datasets.py             # benchmark loader
  api/
    main.py                 # FastAPI endpoints
  cli.py                    # init、demo、benchmark、inspect
tests/
  unit/
  integration/
  fixtures/
experiments/
  datasets/
  configs/
  results/                  # 只提交小型範例，不提交 secrets/raw 大檔
```

核心邏輯不要直接 import 某家 LLM SDK。使用最小 interface：

```python
class LLMProvider(Protocol):
    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class TokenCounter(Protocol):
    def count(self, text: str, model: str | None = None) -> int: ...
```

這樣測試可以用 deterministic fake，不需要每次花 API 成本。

### 3.4 記憶資料模型

所有記憶層共用 `MemoryItem`，避免四套無法比較的 schema：

| 欄位 | 說明 |
| --- | --- |
| `id` | UUID |
| `memory_type` | working / episodic / semantic |
| `scope_id` | user、project、session 或 task 範圍 |
| `content` | 原始內容或摘要 |
| `content_hash` | 去重與 version tracking |
| `source_type` | user / llm / tool / system |
| `source_ref` | 來源 event、message 或 document id |
| `importance` | 0 到 1 |
| `confidence` | 0 到 1 |
| `created_at` | 建立時間 |
| `updated_at` | 最後修改時間 |
| `expires_at` | TTL；可為 null |
| `last_accessed_at` | LRU 使用 |
| `access_count` | LFU 使用 |
| `version` | optimistic update 與 diff |
| `status` | active / superseded / deleted |
| `metadata` | JSON 擴充欄位 |

另外建立：

- `memory_relations`：先只支援 `supersedes`、`conflicts_with`、`derived_from`，不做完整 graph engine。
- `cache_entries`：query、response、embedding reference、scope fingerprint、TTL、hit count、model/config version。
- `runs`：experiment id、policy config、model、input、output、status、timestamps。
- `retrieval_events`：candidate、各子分數、是否採用、token count。
- `metrics`：run id、metric name、value、unit、metadata。

向量資料庫只保存 embedding 與查詢需要的最小 metadata；SQLite 是主要事實來源（source of truth）。

### 3.5 寫入流程

```text
LLM/tool result
  -> 建立 episodic event
  -> 判斷是否值得保存
  -> 抽取候選 semantic facts
  -> 去重與衝突檢查
  -> 寫入 SQLite
  -> 寫入/更新 vector index
  -> 更新 cache 與 metrics
```

第一版的「是否值得保存」可以是規則式：

- 使用者明確說「記住」。
- 內容是偏好、限制、決策、任務結果或可重用事實。
- 排除寒暄、模型內部推測、低 confidence 內容。
- 同 scope 下若 `content_hash` 相同則不重複寫入。

### 3.6 Retrieval 與 ranking

建議流程：

```text
scope/metadata filter
  -> vector top-N candidates
  -> remove expired/superseded items
  -> deduplicate
  -> hybrid rank
  -> token-budget selection
  -> prompt context
```

第一版 hybrid score：

```text
score =
    0.55 * semantic_similarity
  + 0.15 * recency
  + 0.15 * importance
  + 0.10 * confidence
  + 0.05 * frequency
  - pollution_penalty
```

權重先用 config 管理，不要宣稱這組數字最佳。後續用實驗調整。

每個 retrieval result 必須回傳 score breakdown，例如：

```json
{
  "memory_id": "...",
  "final_score": 0.81,
  "semantic_similarity": 0.88,
  "recency": 0.62,
  "importance": 0.90,
  "selected": true,
  "rejection_reason": null
}
```

這是專案的核心可觀察性，不要只回傳一串文字。

### 3.7 Context compression

依成本與風險由低到高實作：

1. **Selection only**：依 score 選入，超過 token budget 就停止。
2. **Extractive compression**：只保留與 query 最相關的句子。
3. **Abstractive summary**：用 LLM 摘要多筆記憶，保留來源 id。

MVP 先完成第 1 種。第 3 種雖然效果可能較好，但會新增一次模型呼叫與 hallucination 風險，必須獨立計入 token、latency 與 cost。

---

## 4. 評估方法與指標

### 4.1 每個指標如何量

| 指標 | 定義 | MVP 計算方式 |
| --- | --- | --- |
| Token Usage | 每個任務實際使用的 token | input + output + embedding + summarization token |
| Cache Hit Rate | 可由 cache 回答的比例 | valid hits / cache lookups |
| Retrieval Precision@k | 取回記憶中真正相關的比例 | relevant retrieved / k；使用標註答案 |
| Retrieval Recall@k | 應取回記憶中被找到的比例 | relevant retrieved / all relevant |
| Latency | 完成任務所需時間 | end-to-end、retrieval、LLM、cache 分開記錄 p50/p95 |
| Task Success Rate | 任務是否正確完成 | deterministic checker、expected facts 或 rubric judge |
| Context Size | 實際送入模型的 context 大小 | token count；另算 compression ratio |
| Cost | 每個任務估計或實際 API 成本 | 依 model price snapshot 與 token 數計算 |
| Memory Pollution | 錯誤記憶對結果造成的影響 | polluted runs 中被錯誤記憶影響的比例 |
| Stale Retrieval Rate | 取回過期/被取代記憶的比例 | stale selected / all selected memories |

`Memory Pollution` 不要只定義成「資料庫中有幾筆錯誤資料」，而應該量它是否進入 prompt、是否改變答案：

```text
pollution_impact_rate =
  incorrect_runs_caused_by_polluted_memory
  / runs_with_polluted_memory_available
```

### 4.2 Baseline 與實驗組

至少比較以下設定：

| 組別 | 設定 |
| --- | --- |
| B0 | Full conversation history，無 memory manager |
| B1 | Fixed recent window，只保留最近 N tokens |
| E1 | Vector top-k memory，無 compression/cache |
| E2 | Hierarchical memory + token budget |
| E3 | E2 + semantic cache |
| E4 | E3 + eviction/pollution handling |

每組應使用相同：

- 任務順序與輸入。
- 模型與推理參數，例如 temperature。
- system prompt version。
- 評分器與資料集版本。
- 至少 3 次重複執行；若溫度為 0，仍需記錄 provider variance 與失敗重試。

### 4.3 測試資料集

第一版自製 30 到 50 組 task sequence 即可，分成：

- `repetition`：同義改寫，測 semantic cache。
- `long_horizon`：答案依賴較早事件，測 episodic retrieval。
- `preference`：依賴使用者偏好，測 semantic memory。
- `update`：舊事實被新事實取代，測 staleness。
- `conflict`：刻意注入錯誤記憶，測 pollution。
- `irrelevant`：加入大量無關內容，測 retrieval precision。

每筆資料至少包含：

```yaml
sequence_id: update-001
turns:
  - input: "專案的部署區域是東京。"
    expected_memory: ["deployment_region=tokyo"]
  - input: "部署區域改成新加坡，請記住。"
    supersedes: ["deployment_region=tokyo"]
  - input: "目前應該部署在哪裡？"
    expected_answer_contains: ["新加坡"]
    relevant_memory_ids: ["deployment_region=singapore"]
```

### 4.4 實驗輸出

每次 benchmark 產生：

```text
experiments/results/<timestamp>-<config-name>/
  config.yaml
  environment.json
  runs.jsonl
  retrievals.jsonl
  metrics.csv
  summary.md
```

`environment.json` 至少記錄 Git commit、Python version、套件版本、model id 與 price snapshot date，避免幾個月後無法解釋數字。

---

## 5. 工程與協作基礎

### 5.1 Git 與 repository 規則

初始化時完成：

- 建立 Git repository 與 GitHub/GitLab remote。
- 預設分支使用 `main`。
- 功能分支採 `feat/...`、`fix/...`、`docs/...`。
- commit 保持小而可讀，例如 `feat: add ttl eviction policy`。
- 設定 `.gitignore`，排除 `.env`、SQLite runtime data、vector index、大型 experiment output。
- 提供 `.env.example`，只放變數名稱與安全範例。
- 使用 GitHub Actions 執行 lint、type check、test。

任何 API key 都不能進 Git history。若誤提交，不能只刪目前檔案，還需要撤銷並重新產生該 key。

### 5.2 測試策略

| 層級 | 要測什麼 |
| --- | --- |
| Unit | score、TTL、LRU、token budget、dedupe、cache key |
| Integration | SQLite 與 vector index 一致性、完整 write/retrieve 流程 |
| Contract | fake provider 與真實 provider adapter 回傳相同 domain model |
| Evaluation smoke | 小型固定 dataset 能端到端跑完且產生 metrics |
| Regression | 過期記憶、衝突記憶、cache scope 等已知失敗案例 |

最重要的邊界案例：

- SQLite 寫入成功但 vector index 寫入失敗。
- memory 已被 supersede，但 vector DB 仍查得到舊 embedding。
- cache similarity 很高，但 system prompt/model/context 已改變。
- summary 丟失否定詞、數字、日期或來源。
- token budget 小於單筆最高優先記憶。
- 同時執行兩個 session 時 scope 串資料。

### 5.3 README 必備內容

專案首頁的 README 應包含：

1. 問題與一句話解法。
2. 一張簡潔架構圖。
3. 30 到 60 秒 demo GIF 或截圖。
4. 核心功能與非目標。
5. Quickstart，包含 fake provider 的零成本路徑。
6. 真實 LLM provider 的環境變數設定。
7. 一條可重現 benchmark 的指令。
8. 代表性實驗表格與失敗案例。
9. API/CLI 範例。
10. Roadmap、license 與限制。

作品集的說服力主要來自「可重現的數字 + 能解釋的設計取捨」，不是功能數量。

### 5.4 建議 CLI 介面

```bash
memlite init
memlite demo --provider fake
memlite run --task "Remember that I prefer concise answers."
memlite inspect memories --scope demo-user
memlite inspect cache
memlite benchmark --config experiments/configs/mvp.yaml
memlite report experiments/results/<run-id>
```

### 5.5 建議 API

```text
POST   /v1/tasks
POST   /v1/memories
GET    /v1/memories
PATCH  /v1/memories/{id}
DELETE /v1/memories/{id}
POST   /v1/retrieval/query
GET    /v1/cache
DELETE /v1/cache/{id}
GET    /v1/runs/{id}
GET    /v1/runs/{id}/trace
GET    /health
```

MVP 不需要一開始就完成全部 API。先讓 domain service 與 CLI 工作，再薄薄包一層 FastAPI。

---

## 6. 部署與上線

### 6.1 部署目標

公開版本至少包含：

- 可瀏覽的 README 與架構圖。
- 可執行的 API 或互動 demo。
- `/health` health check。
- 不需要使用者提供個人 API key 也能觀看的 sample run/report。
- 清楚標示 demo 的限制與資料保留方式。

### 6.2 建議部署方案

第一版優先使用 **Zeabur + Docker**：

- 部署 FastAPI 與 Streamlit demo。
- 掛載 persistent volume 保存 SQLite 與 Chroma 資料。
- API key 使用平台 secret/environment variable。
- demo 預設使用限制額度或 fake/precomputed mode，避免公開端點產生無上限成本。

也可以選擇：

- Vercel/Cloudflare Pages：只部署靜態報告或前端。
- Render/Railway/Fly.io：部署容器化 API。
- Qdrant Cloud/Supabase pgvector：未來需要外部向量資料庫時再加入。

SQLite 與 local vector store 需要持久磁碟；若平台只有 ephemeral filesystem，重新部署後資料會消失。這必須在選平台時先確認。

### 6.3 上線前檢查

- [ ] Docker image 可在全新環境啟動。
- [ ] migration 會在啟動時安全執行。
- [ ] `/health` 能分辨 API、SQLite、vector store 狀態。
- [ ] secret 未寫入 image、log 或 repository。
- [ ] 設定 request timeout、rate limit 與最大 token budget。
- [ ] demo 資料與真實使用者 scope 隔離。
- [ ] 有資料備份或清楚標示 demo data 可被重設。
- [ ] 錯誤訊息不暴露 prompt、API key 或完整個資。

---

## 7. 建議開發里程碑

### Milestone 0：定義與骨架（1 到 2 天）

- [ ] 建立 repository、license、`.gitignore`、`.env.example`。
- [ ] 建立 Python package、pytest、Ruff、mypy。
- [ ] 寫第一版 README 與 architecture decision records（ADR）。
- [ ] 固定第一個 use case 與 10 組 benchmark sequences。

驗收：`pytest`、lint 與 CLI hello-world 在本機和 CI 都能通過。

### Milestone 1：可用的 Memory Manager（3 到 5 天）

- [ ] 建立 SQLite schema 與 migration。
- [ ] 完成 Working/Episodic/Semantic CRUD。
- [ ] 完成 Chroma adapter 與 embedding fake。
- [ ] 完成 top-k retrieval、scope filter、trace。
- [ ] 處理 SQLite/vector index 部分失敗與重建索引。

驗收：一個 task sequence 能寫入記憶，再從新 session 正確找回指定記憶。

### Milestone 2：Compression 與 Semantic Cache（3 到 5 天）

- [ ] 實作 token-budget selection。
- [ ] 實作 exact cache 與 semantic cache。
- [ ] 實作 threshold、TTL、invalidation、scope fingerprint。
- [ ] 實作 TTL 與 LRU eviction。

驗收：同義改寫可命中 cache；背景或 model version 改變時不會錯誤命中。

### Milestone 3：Evaluation（4 到 7 天）

- [ ] 擴充至 30 到 50 組 benchmark sequences。
- [ ] 建立 B0/B1/E1/E2/E3 實驗組。
- [ ] 計算 token、cache、retrieval、latency、success、pollution 指標。
- [ ] 產生 CSV/JSON 與 `summary.md`。

驗收：一條指令可以從乾淨資料庫跑完小型 benchmark 並產生比較表。

### Milestone 4：作品集展示（3 到 5 天）

- [ ] 建立 memory inspector 與 run trace UI。
- [ ] 顯示 score breakdown、cache decision、token/cost 對照。
- [ ] 補齊 README、架構圖、demo GIF。
- [ ] 加入一個誠實的 failure analysis。

驗收：不了解程式碼的人可以從 UI 說出某次回答用了哪些記憶，以及 MemLite 是否省下成本。

### Milestone 5：部署與發布（2 到 3 天）

- [ ] 建立 Dockerfile/Compose。
- [ ] 部署 API 與 demo。
- [ ] 設定 volume、secret、rate limit、health check。
- [ ] 建立 release tag 與公開 benchmark 結果。

驗收：從公開連結可以看 demo；依 README 可在另一台電腦重現 sample benchmark。

---

## 8. 第一週的具體待辦

不要同時開五條線。照這個順序開始：

- [ ] Day 1：確認 use case、非目標、10 組 task sequences。
- [ ] Day 2：建立 package、CI、domain models 與 fake providers。
- [ ] Day 3：建立 SQLite schema、repository 與 migration。
- [ ] Day 4：實作 Working/Episodic/Semantic Memory CRUD。
- [ ] Day 5：串接 vector store，完成帶 trace 的 top-k retrieval。
- [ ] Day 6：補 unit/integration tests 與 index rebuild。
- [ ] Day 7：錄製第一個「寫入 -> 關閉 -> 重開 -> 找回」demo，整理問題清單。

第一週結束時先做一次 scope review：若基本 retrieval 還不穩定，不開始 UI、semantic cache 或摘要。

---

## 9. 重要設計決策紀錄（ADR）

建議在 `docs/adr/` 逐項建立短文件：

- `0001-sqlite-as-source-of-truth.md`
- `0002-separate-metadata-and-vector-index.md`
- `0003-provider-agnostic-core.md`
- `0004-cache-scope-and-invalidation.md`
- `0005-memory-versioning-and-supersession.md`
- `0006-evaluation-baselines.md`

每份 ADR 只需包含 Context、Decision、Consequences。這能讓面試官看到你不只會接 API，也能說清楚系統取捨。

---

## 10. 風險與對策

| 風險 | 對策 |
| --- | --- |
| 專案變成大型 Agent framework | Agent loop 保持最小；功能必須對應研究問題 |
| 評估只靠主觀感覺 | 先做可 deterministic 判分的資料，再增加 LLM judge |
| Semantic cache 回錯答案 | scope fingerprint、TTL、threshold、rejected-hit log |
| 摘要產生錯誤 | 保留 source ids；關鍵事實使用 extractive 或 structured format |
| SQLite 與 vector index 不一致 | SQLite 作 source of truth；提供 idempotent reindex command |
| API 成本不可控 | fake provider、precomputed demo、budget cap、rate limit |
| 結果無法重現 | 保存 config、commit、model、seed、price snapshot、raw run log |
| UI 花太多時間 | CLI 與 report 先完成，UI 排到 P1 |

---

## 11. 現在要做的第一個決策

在開始寫核心程式前，先把以下內容填好並提交到 repository：

```yaml
project_positioning: portfolio_with_research_evaluation
primary_use_case: personal_research_assistant
primary_language: python
metadata_store: sqlite
vector_store: chroma
first_real_llm_provider: openai
offline_test_provider: deterministic_fake
mvp_core_features:
  - hierarchical_memory_lifecycle
  - semantic_cache
  - evaluation_and_tracing
first_eviction_policies:
  - ttl
  - lru
context_compression_v1: token_budget_selection
deployment_target: zeabur_docker
```

接著先建立 10 組 benchmark task sequences。資料集會反過來約束 API 與 schema，讓開發不會只剩下抽象的「做一個 memory system」。

---

## 參考資料

- [關於 Side Project 的小小經驗談](https://medium.com/@Kelly_CHI/how-to-side-project-%E9%97%9C%E6%96%BC-side-project-%E7%9A%84%E5%B0%8F%E5%B0%8F%E7%B6%93%E9%A9%97%E8%AB%87-65b160f331b3)
- [要不要來點 Side Project 啊？](https://codlin.me/blog-program/do-you-want-to-do-a-side-project)
- [腦中有許多想法，開了 Side Project 卻永遠做不完，這過程中出了什麼問題？](https://aapd.com.tw/all-articles/why-side-projects-never-finish)
- [Zeabur](https://zeabur.com/)

