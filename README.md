# MemLite-Agent

MemLite-Agent 是一個提供給 LLM Agent 使用的輕量化分層記憶與語意快取系統。它把記憶視為可查看、可修改、可追蹤與可評估的外部狀態，而不是無限制保留完整對話。

**作者：陳格洋 | Python 3.11+ | SQLite | MIT | 離線研究原型與 Codex skill**

離線核心、demo 與基準不需要 API key。套件安裝目前包含 API 與真實 provider 的依賴；真實 adapter 的程式存在，但遠端效果尚未驗證。

## 三十秒認識

### 一個指令安裝 Codex skill

先安裝 Node.js（含 npm/npx）與 Git，再執行：

```bash
npx --yes skills@1.7.0 add https://github.com/Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents/tree/main/docs/skills/memlite-agent --agent codex --global --copy
```

只安裝 `memlite-agent`，不會安裝專案的其他 skills；`--copy` 避免 Windows symlink 權限需求。參數依 [官方 skills CLI](https://github.com/vercel-labs/skills) 並以 1.7.0 實測。指令會取得並執行第三方 CLI，使用前請確認來源；已有同名 skill 請先備份／比較，不要直接覆蓋。private repo 仍需要 GitHub 存取權與已設定的 Git 登入，請勿把 token 貼到指令或對話。

**此指令安裝 skill，不包含 Python 記憶引擎。** 第一次使用請完成下方「快速開始」，在 Codex 開啟下載的專案後輸入 `使用 $memlite-agent`。完整安裝、檢索與修正教學見 [Skill 使用指南](docs/SKILL_USAGE.zh-TW.md)。核心與手動安裝不需要 Node.js；只有這個 npx 安裝入口需要。

| 你想做什麼 | 從哪裡開始 |
| --- | --- |
| 讓 Codex 儲存、檢索、修正與忘記本地記憶 | [Skill 安裝與五分鐘教學](docs/SKILL_USAGE.zh-TW.md) |
| 看記憶、快取與 Agent 六步流程 | 下方快速開始，執行 `python -m memlite.demo` |
| 繼續研究或重現策略比較 | [PROGRESS.md](PROGRESS.md)、[重要記憶保護實驗](docs/IMPORTANCE_PROTECTION_20261005.zh-TW.md) |
| 準備分享至 GitHub | [Private → Public 驗收清單](docs/RELEASE_CHECKLIST.zh-TW.md) |

目前已驗證本地記憶 lifecycle、context 快取隔離、候選補足與有上限的重要記憶保護。**不是已證明能降低真實 LLM 成本的正式服務**，也不是自動記錄所有對話的個人記憶產品。最新完整進度以 [PROGRESS.md](PROGRESS.md) 為準。2026-10-06 核對 GitHub 時 repo 已是 public，本輪沒有更改 visibility；尚未發布 GitHub Release 或公開 API。

## 架構

```
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
   |        +-----------> Vector DB
   +--------------------> SQLite
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

## 目前功能

### 記憶管理
- Working、Episodic、Semantic 三種記憶型別
- SQLite 持久化與自動建表
- 依 scope 與記憶型別查詢
- TTL 過期控制
- 相同內容去重
- `supersedes` 關係與舊記憶失效

### 向量檢索
- 向量檢索、hybrid score breakdown 與 token-budget selection
- 檢索結果依 SQLite metadata 再驗證 scope/type、狀態與 TTL
- 拒絕無效評分設定，排除重複及非有限分數候選

### 語意快取 (Semantic Cache)
- Exact match + semantic similarity 雙層快取查找
- `cache_scope` 指紋（hash of system_prompt_version, model_id, tool_schema_version, context_fingerprint）
- 可調 similarity threshold
- TTL 過期與手動 invalidation
- hit / miss / rejected_hit 事件記錄
- Scope fingerprint 不同時自動拒絕命中，防止跨 context 快取污染

### 淘汰策略 (Eviction Policies)
- **TTL** — 清除過期條目
- **LRU** — 容量超限時淘汰最久未存取的記憶
- **LFU** — 容量超限時淘汰存取次數最少的記憶
- **Hybrid** — 先 TTL 清理，再 LRU/LFU 容量控制
- **ImportanceProtectedEviction**：可選擇保留少量高重要性、高信心記憶，仍遵守總容量與 TTL；不是預設，也不驗證事實真偽。

### Provider 抽象
- LLMProvider / TokenCounter / EmbeddingProvider protocols
- Deterministic fake providers（無 API 成本的離線測試）

### 評測
- 固定資料集與策略／token budget／語料大小比較
- 可直接使用的 CLI
- 不需要 API key 的離線測試

## 快速開始

需求：Python 3.11 以上；引擎本身不需要 Node.js 或 RTK。下載後先在 repo 根目錄建立環境：

```bash
git clone https://github.com/Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents.git memlite-agent
cd memlite-agent
python -m venv .venv
```

Windows PowerShell：

```powershell
.venv/Scripts/python.exe -m pip install -e "."
.venv/Scripts/python.exe -X utf8 -m memlite.demo
```

macOS / Linux：

```bash
.venv/bin/python -m pip install -e "."
.venv/bin/python -m memlite.demo
```

demo 使用獨立臨時資料庫，fake-provider 回覆不是回答品質評測。尚未公開前，clone 需要 GitHub 存取權；也可下載 repo ZIP 後在解壓的根目錄安裝。

下列 `python` 與 `memlite` 指令需在該環境中執行。未啟用環境時，將 `python` 換成上面的完整 Python 路徑；CLI 可用 `python -m memlite`。

```bash
# 安裝
python -m pip install -e .

# 初始化資料庫
memlite --db data/memlite.db init

# 儲存記憶
memlite --db data/memlite.db remember \
  --scope demo-user \
  --type semantic \
  --content "這個專案只能使用 MIT 或 Apache-2.0 授權套件"

# 查詢記憶
memlite --db data/memlite.db recall --scope demo-user
```

### 向量檢索 CLI

```bash
# 儲存並索引記憶
python -m memlite.retrieval_cli remember \
  --scope demo-user --type semantic \
  --content "回答時請使用繁體中文"

# 可解釋的向量檢索（含 score breakdown）
python -m memlite.retrieval_cli retrieve \
  --scope demo-user --query "我偏好什麼語言？"
```

### Python API

```python
from memlite.engine import MemLiteEngine
from memlite.cache import ScopeContext
from memlite.models import MemoryType
from memlite.policies.eviction import LRUEviction

with MemLiteEngine("data/memlite.db", eviction_policy=LRUEviction(max_items=100)) as engine:
    # 儲存記憶
    engine.remember(
        memory_type=MemoryType.SEMANTIC,
        scope_id="demo",
        content="部署區域是新加坡",
    )

    # 向量檢索（含 score breakdown）
    response = engine.retrieve("部署在哪裡？", scope_id="demo")
    for candidate in response.candidates:
        print(candidate.score.to_dict())

    # 語意快取
    ctx = ScopeContext(model_id="gpt-4o", system_prompt_version="v2")
    engine.cache_store("What DB?", "SQLite", scope_id="demo", scope_context=ctx)
    result = engine.cache_lookup("What DB?", scope_id="demo", scope_context=ctx)

    # 執行淘汰
    eviction_result = engine.run_eviction("demo")
```

## 執行測試

目前有 139 個測試（另有 62 個 subtests），API 測試使用 FastAPI TestClient。安裝開發依賴後執行：

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m mypy memlite
```

## 執行 Benchmark

```bash
# 檢索基準
python -m memlite.benchmark_cli --summary-only

# 策略比較（含 token budget 與 latency）
python -m experiments.run_comparisons --output experiments/results/my-run

# 長歷史、多必要事實與 eviction 受控實驗（固定資料集，至少三次重複）
python -m memlite.evaluation.challenge_benchmark --output experiments/results/my-challenge --repeats 3

# 候選補足的固定資料配對驗證（控制組與修正組各重複三次）
python -m experiments.run_refill_comparison --output experiments/results/my-refill --repeats 3

# 重要記憶保護：22 案例、13 策略，保留改善與退步
python -m memlite.evaluation.protection_benchmark --output experiments/results/my-protection --repeats 3

# Agent L2 壓縮：6 案例、完整 context 與 5 種預算，衡量必要事實保留
python -m memlite.evaluation.compression_benchmark --output experiments/results/my-compression --repeats 3

# 離線 Agent 六步示範
python -m memlite.demo

# 直接匯出 UTF-8，避免 shell 轉碼；既有檔案需明確 --overwrite
python -m memlite.demo --output docs/demo_output.txt --overwrite
```

## 檢索篩選語意

`memory_types=None` 表示不限型別；空集合 `set()` 表示不選任何型別，回傳空結果。此規則適用於 metadata store、vector index 與 retrieval service。

`candidate_limit` 計算通過 metadata 檢查的有效候選。過期或其他無效 hit 不足以填滿候選時，
會擴大搜尋前綴；`candidate_scan_limit` 可限制前綴深度，未指定時為 max(100000, candidate_limit)。
`scan_limit_reached` 為 true 時，候選池可能被截斷；它不代表一定存在漏掉的正解。
trace 同時提供 `search_rounds`、`scanned_hits`（最後返回的前綴長度）與 `search_limit`。
原始向量搜尋 API 不變，backend 必須在擴大 limit 時保留排序前綴。
詳見 [候選補足研究紀錄](docs/RETRIEVAL_REFILL_20261004.zh-TW.md)。

## Agent 壓縮與記憶修正

`PromptBuilder(memory_token_budget=32)` 可選用抽取式 L2 壓縮，只壓縮實際選入的記憶，不改寫 SQLite 原文，也不限制 system instruction 或對話歷史的 token。Agent 的 cache context 指紋包含壓縮後內容；預設不啟用，亦不會呼叫摘要 API。

```python
from memlite.agent.loop import AgentLoop
from memlite.agent.prompt_builder import PromptBuilder

agent = AgentLoop(engine, llm_provider, PromptBuilder(memory_token_budget=32))
```

32 不是通用建議值，僅為示例。六個壓力案例中，budget 32 保留全部必要事實的題目為 5/6，長句仍被丟失；budget 128 在這些案例沒有壓縮收益。詳見 [壓縮整合與研究報告](docs/COMPRESSION_AND_CORRECTION_20261005.zh-TW.md)。

`supersede` 保留記憶的原始絕對到期時間，並保留舊版本；過期記憶不能藉修正復活。skill 修正可附新 `source` / `source_ref`，但不會自動驗證事實或找出全部矛盾。

L3 可用 `PromptBuilder(memory_token_budget=200, compression_strategy="abstractive")` 選用，由 Agent 注入 provider；摘要模型預設沿用 `run(model_id=...)`，也可明確指定 `summary_model`。獨立使用 builder 時必須提供 provider，缺少時會拒絕執行，不默默跳過壓縮。

L3 快取先核對原始選入 context、摘要模型及預算，命中後不再呼叫摘要。成功回傳的 token 用量包含摘要與主回答；`result.metadata["provider_calls"]` 分別列出階段、provider 回報模型、requested_model、用量與延遲。不同模型應分別套用價格，不能只將總 token 套到主模型單價。provider 失敗或缺少 usage 時仍須另行核對實際用量，不能假設零費用。

`auto_extract=True` 是明確選用的關鍵字抽取，不會自動啟用；cache hit 也會執行授權的抽取。抽出的是 LLM 句子，使用 confidence 0.7，不代表事實已被確認；矛盾、個資與污染評估仍待完成。

API 的 `MEMLITE_TOKEN_BUDGET` 僅為每個 scope、process-local 的成功請求輸入估計配額；失敗操作會退回預留值，重啟不保留。它不是 Agent、embedding 或摘要的實際成本上限，也不提供登入／scope 授權。

## 設計決策

架構決策紀錄（ADR）位於 [`docs/adr/`](docs/adr/)：

1. SQLite 作為 source of truth
2. Provider-agnostic core
3. 分離 metadata 與 vector index
4. Cache scope 與 invalidation 策略
5. Memory versioning 與 supersession
6. Evaluation baselines
7. Metadata-aware candidate refill
8. Bounded importance protection

## 最新研究摘要

重要記憶保護固定 importance / confidence 門檻 0.8、保留 1 個名額，測試 capacity 2/4/8 的 LRU/LFU 配對比較：22 個 synthetic 案例 × 13 策略 × 3 次，共 858 筆 trace。36 筆改善、24 筆退步，沒有容量違規。退步原因是錯誤記憶也可能被標為高重要性、高信心，因此策略保持 opt-in，沒有取代預設。重複不是獨立樣本，retrieval pass 不是 LLM task success。詳細表格、規則、checksum 與重現方式見 [研究報告](docs/IMPORTANCE_PROTECTION_20261005.zh-TW.md)。

## 下一步

1. 來源／證據與衝突治理，避免將高重要性誤當成真實性；保護首輪實驗已完成。
2. 在目前 synthetic 壓力案例之外建立獨立、貼近實際任務的 held-out dataset。
3. 真實 embedding／LLM 的品質、token、延遲與成本評估。
4. L2/L3 串接與成功回傳的用量追蹤已有；補上真實回答品質、失敗呼叫與實際費用評測。
5. UI、Docker 容器驗收、使用者授權與公開展示。

## Codex Skill

新增 `memlite-agent` skill，支援具 scope 的本地記憶管理與依 `PROGRESS.md` 接續研究。
原始碼位於 [`docs/skills/memlite-agent/`](docs/skills/memlite-agent/)，使用方式見
[`docs/SKILL_USAGE.zh-TW.md`](docs/SKILL_USAGE.zh-TW.md)。
使用範例：`使用 $memlite-agent，讀取 PROGRESS.md，接續下一個研究切片並完成測試與紀錄。`
skill 不會自動記錄對話或呼叫付費 API。

在 Codex 中安裝（遠端需要已 push 的檔案與 repo 存取權）：

```text
使用 $skill-installer，從 Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents 的 main 分支安裝 docs/skills/memlite-agent，不要覆蓋既有同名 skill。
```

也可使用 README 開頭的 npx 一行安裝。skill 與 runtime 分開安裝；先完成上方快速開始，再依 [完整教學](docs/SKILL_USAGE.zh-TW.md) 操作。維護者可執行 `python -m experiments.package_skill --output dist/memlite-agent-skill.zip` 產生附 manifest、授權與教學的下載包；不含記憶資料庫，且拒絕覆蓋舊包。GitHub push、安裝與 CI 的實際驗收狀態見 [PROGRESS.md](PROGRESS.md)，Release 與轉 public 不會自動執行。

## 限制

- 已驗證結果使用 deterministic lexical embedding；OpenAI adapter 存在但未連線驗證。
- Agent Loop 可執行 fake-provider demo；fake 回覆只是確認訊息，不能當成回答品質證據。
- Cache 已驗證 context 隔離與重複任務；真實語意改寫命中的正確性仍待研究。
- API 為本機研究展示用，目前沒有使用者驗證、scope 授權或成本 budget cap。
- SQLite + local vector store 需要持久磁碟
- 不支援多 Agent orchestration 或 Graph Memory

2026-10-06 已修正快取抽取、L3 額外呼叫／漏記用量與錯誤配額扣款，並修復 demo 編碼。尚未完成的六項所需資料、授權與環境見 [剩餘工作與條件](docs/FIXES_AND_REQUIREMENTS_20261006.zh-TW.md)。公開 repo／Release 仍由維護者決定。

## License

[MIT](LICENSE)。

完整規劃請見 [PROJECT_GUIDE.md](PROJECT_GUIDE.md)。
強化報告見 [docs/IMPLEMENTATION_HARDENING.zh-TW.md](docs/IMPLEMENTATION_HARDENING.zh-TW.md)。
