# MemLite-Agent

MemLite-Agent 是一個提供給 LLM Agent 使用的輕量化分層記憶與語意快取系統。它把記憶視為可查看、可修改、可追蹤與可評估的外部狀態，而不是無限制保留完整對話。

核心不需要 API key 或第三方執行期套件。

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

### Provider 抽象
- LLMProvider / TokenCounter / EmbeddingProvider protocols
- Deterministic fake providers（無 API 成本的離線測試）

### 評測
- 固定資料集與策略／token budget／語料大小比較
- 可直接使用的 CLI
- 不需要 API key 的離線測試

## 快速開始

需求：Python 3.11 以上。

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

核心測試只使用 Python 標準函式庫（46 個測試）：

```bash
python -m unittest discover -s tests -v
```

## 執行 Benchmark

```bash
# 檢索基準
python -m memlite.benchmark_cli --summary-only

# 策略比較（含 token budget 與 latency）
python experiments/run_comparisons.py
```

## 檢索篩選語意

`memory_types=None` 表示不限型別；空集合 `set()` 表示不選任何型別，回傳空結果。此規則適用於 metadata store、vector index 與 retrieval service。

## 設計決策

架構決策紀錄（ADR）位於 [`docs/adr/`](docs/adr/)：

1. SQLite 作為 source of truth
2. Provider-agnostic core
3. 分離 metadata 與 vector index
4. Cache scope 與 invalidation 策略
5. Memory versioning 與 supersession
6. Evaluation baselines

## 下一步

1. Agent Loop + Prompt Builder — 讓 demo 可以端到端跑 task sequence
2. 擴充 benchmark dataset 到 30+ 組
3. 加入 B0/B1 baseline（full history 與 recent window）
4. FastAPI 薄層 + Docker 部署
5. 加入真實 embedding provider 並與離線基準比較

## 限制

- 目前只支援離線 deterministic embedding，不做真正的語意匹配
- 沒有 Agent Loop，只能單獨操作記憶與快取
- SQLite + local vector store 需要持久磁碟
- 不支援多 Agent orchestration 或 Graph Memory

## License

MIT

完整規劃請見 [PROJECT_GUIDE.md](PROJECT_GUIDE.md)。
強化報告見 [docs/IMPLEMENTATION_HARDENING.zh-TW.md](docs/IMPLEMENTATION_HARDENING.zh-TW.md)。
