# MemLite-Agent 逐檔架構導讀

核對日期：2026-09-14。對象：專題指導教授與口試委員。依目前原始碼說明；規劃文件不代表功能已完成。

## 1. 專題定位

教授您好，MemLite-Agent 研究的是：Agent 有大量歷史資料時，如何保存有效記憶、排除過期或錯誤資料，並在有限 context 預算內選出相關資訊。

目前交付物是可離線執行的 Python 記憶管理與檢索原型，以及固定資料集上的比較實驗。核心執行期沒有第三方依賴，尚未接入真正 LLM 回答流程。

Working、Episodic、Semantic 目前是同一資料模型中的三種分類，可依型別篩選；並非三套各自具備自動整理、搬移或摘要機制的記憶系統。

## 2. 程式如何串接

```text
基本管理：python -m memlite
  -> __main__.py -> cli.py -> MemoryManager -> MemoryStore -> SQLite metadata

向量檢索：python -m memlite.retrieval_cli
  -> retrieval_cli.py -> MemLiteEngine
      -> MemoryManager -> SQLite metadata（內容、狀態與關係）
      -> EmbeddingProvider -> SQLiteVectorIndex（可重建的索引）
      -> RetrievalService（再驗證、評分、預算選取與原因）

實驗：benchmark_cli.py / experiments/run_comparisons.py
  -> evaluation -> 固定資料集 -> MemLiteEngine -> 指標 / JSON / CSV
```

SQLite metadata 是主要事實來源。向量索引只負責提供候選，不能自行決定某筆記憶是否有權被讀取或仍然有效。

## 3. 根目錄檔案

| 檔案 | 實際用途與教授可檢視的重點 |
| --- | --- |
| `README.md` | 專案入口，介紹現有能力、安裝、CLI 與測試方式。適合第一次閱讀。 |
| `PROJECT_GUIDE.md` | 原始完整提案，包含動機、MVP、技術選型、研究指標與部署方向。內含未實作設計與範例介面。 |
| `pyproject.toml` | 套件名稱、作者、Python >=3.11、建置工具、CLI 入口及 pytest/Ruff/mypy 設定。執行期 dependencies 為空，開發工具放在 dev 群組。 |
| `.env.example` | 環境變數範本，預留 API key 與 DB 路徑；本檔不會自動載入，也不代表 LLM adapter 已實作。 |
| `.gitignore` | 排除虛擬環境、快取、私密環境檔、資料庫及實驗輸出。原始結果目前保留本機，不會自動隨 Git 提交。 |

## 4. 核心模型與入口

| 檔案 | 職責 |
| --- | --- |
| `memlite/models.py` | 定義 MemoryItem、三種 MemoryType、來源與狀態 enum；處理 UUID、UTC 時間、內容正規化、SHA-256 去重鍵、欄位驗證、過期判断與 JSON 可用資料。 |
| `memlite/manager.py` | 記憶生命週期：remember、recall、supersede、forget；檢查 TTL、交給 store 保存、讀取後增加存取次數、建立替代記憶。自身不產生向量。 |
| `memlite/engine.py` | 高階整合入口 MemLiteEngine；組裝 manager、embedding、vector index 與 retrieval。寫入後建立索引，替代/刪除時同步向量，提供 scope 索引重建。 |
| `memlite/cli.py` | 基本命令列 init/remember/recall/supersede/forget，輸出 JSON。使用 manager，因此不會自動更新向量索引。 |
| `memlite/retrieval_cli.py` | 整合向量的 remember/retrieve/supersede/forget/reindex 命令；使用 engine，適合展示檢索分數與選取原因。 |
| `memlite/benchmark_cli.py` | 執行固定資料集基準，提供摘要或逐題 JSON 結果。 |
| `memlite/__main__.py` | 讓 `python -m memlite` 能呼叫基本 CLI。 |
| `memlite/__init__.py` | 定義套件頂層公開匯出，例如 MemoryManager、MemoryItem、SQLiteMemoryStore；Engine 目前從 memlite.engine 匯入。 |

基本 CLI 寫入的記憶若要供向量搜尋使用，需要再透過 retrieval CLI 的 reindex 建立索引。recall 是依重要性與更新時間列出有效記憶，retrieve 才會接收問題文字並進行向量檢索。

## 5. 儲存與向量層

| 檔案 | 職責 |
| --- | --- |
| `memlite/storage/base.py` | MemoryStore Protocol：宣告 save/get/list_active/touch/replace/soft_delete/close，讓核心邏輯可替換儲存實作。 |
| `memlite/storage/sqlite.py` | 實作 SQLite metadata store，自動建表、索引、WAL、外鍵、參數化 SQL、持久化、去重、TTL 篩選、軟刪除與替代關係。 |
| `memlite/storage/__init__.py` | 匯出 MemoryStore 與 SQLiteMemoryStore。 |
| `memlite/embeddings/base.py` | EmbeddingProvider Protocol：model_id、dimension、embed(texts)，定義文字轉向量介面。 |
| `memlite/embeddings/deterministic.py` | DeterministicHashEmbedding：以英文詞、相鄰詞、中文字與雙字特徵做雜湊，預設 256 維並正規化。適合離線可重現測試，主要捕捉詞彙重疊，沒有經過語意模型訓練。 |
| `memlite/embeddings/__init__.py` | 匯出 provider 介面與離線實作。 |
| `memlite/vector/base.py` | VectorIndex Protocol 與 VectorSearchHit，宣告向量更新、刪除、scope 清除與搜尋介面。 |
| `memlite/vector/sqlite.py` | 將向量以 JSON 存入 SQLite；依 scope、model、dimension、type 篩選後，以 Python 計算點積並完整排序。是 exact-search baseline，尚未使用 ANN 或 Chroma。 |
| `memlite/vector/__init__.py` | 匯出向量索引介面、搜尋結果型別及 SQLite 實作。 |

metadata DB 的 `memories` 保存內容、來源、重要性、可信度、TTL 與狀態；`memory_relations` 保存新記憶 supersedes 舊記憶的關係。vector DB 的 `memory_vectors` 保存 embedding 與最低限度查詢欄位。

metadata 替代操作在同一 DB 交易中完成，但 metadata DB 與 vector DB 的更新尚非跨庫原子操作。reindex_scope 可以重建索引，仍缺持久化失敗追蹤與自動修復。

## 6. 檢索策略

`memlite/policies/retrieval.py` 是主要演算法檔案：

1. RetrievalConfig 定義候選數、結果數、token budget、相似度門檻、評分權重與時間衰減。
2. RetrievalService 將 query 轉成向量並取得候選。
3. 回到 metadata 驗證 scope、型別、active 狀態與 TTL；排除重複 ID、NaN 與 Infinity 分數。
4. 計算分數後排序，依門檻、結果上限及 token 預算逐筆選取。
5. 回傳 ScoreBreakdown、候選資訊、選取 ID 與拒絕原因；僅更新選入記憶的存取紀錄。

預設公式如下，各項與最終結果均依實作限制範圍：

```text
score = 0.55 * similarity + 0.15 * recency
      + 0.15 * importance + 0.10 * confidence
      + 0.05 * frequency - pollution_penalty
```

recency 使用更新時間與 30 天半衰期；frequency 使用存取次數的對數縮放。pollution_penalty 是外部寫入 metadata 的人工訊號，並非系統自動偵測錯誤記憶。

Token 估算為 `max(1, ceil(UTF-8 bytes / 4))`，只計選入記憶內容，沒有計算 system prompt、query 或模型輸出。選取方式為依分數的貪婪選取，並未求全域最佳組合。

`memlite/policies/__init__.py` 匯出上述設定、服務、回應、候選與評分型別。

## 7. 評估與原始資料

| 檔案 | 職責 |
| --- | --- |
| `memlite/evaluation/datasets.py` | 定義 BenchmarkDataset/Sequence、載入 JSON，檢查版本、非空序列、重複序列 ID、預期答案與必要情境類別。不是完整 JSON Schema 驗證器。 |
| `memlite/evaluation/retrieval_benchmark.py` | 用臨時 DB 回放記憶寫入/替代與查詢；逐題計算 Precision、Recall、Reciprocal Rank、pass 與延遲，彙整結果。 |
| `memlite/evaluation/comparison_benchmark.py` | 比較 5 種策略、6 種 token budget、5 種語料大小；計算 P50/P95 並輸出 JSON 與 3 份 CSV。每個語料大小暖機後量測 30 次。 |
| `memlite/evaluation/__init__.py` | 匯出資料集型別與載入函式。 |
| `experiments/datasets/mvp.json` | 版本 1.0.0 的人工固定資料集，10 個查詢，涵蓋重複、長期、偏好、更新、衝突、無關資訊與 scope 隔離。含 expected/forbidden memory keys。 |
| `experiments/run_comparisons.py` | 一次執行全部比較的腳本，將結果寫入 experiments/results/current。 |
| `experiments/results/current/comparison.json` | 彙整策略、budget、語料延遲三組測量結果與基準限制。 |
| `experiments/results/current/strategy_comparison.csv` | 五種檢索策略的指標表，供圖表使用。 |
| `experiments/results/current/token_budget_comparison.csv` | 預算 8/16/32/64/128/500 下的品質與估算 token 比較。 |
| `experiments/results/current/corpus_latency_comparison.csv` | 10/100/500/1000/2000 筆記憶的 P50/P95 延遲。 |
| `experiments/results/hardening-20260914/before.json` | 檢索邊界強化前的固定基準紀錄。 |
| `experiments/results/hardening-20260914/after.json` | 強化後的對照紀錄，用以檢查行為改動是否影響基準。 |
| `experiments/results/.gitkeep` | 讓 Git 保留空結果資料夾；本身沒有測量內容。 |

pass 的實際定義是「選入所有 expected memories，而且沒有任何 forbidden memories」。不禁止其他未標成 forbidden 的多餘候選；Precision 另行衡量多取資訊的問題。這是檢索通過率，不能直接當作 LLM 回答成功率。

先前 Hybrid Top-1 的 80% 表示 10 個檢索案例通過 8 個；27.6% 是相對 Hybrid Top-5 的選入記憶估算 token 減少量。它們並不是完整 API token 或成本節省結果。

## 8. 測試檔案

| 檔案 | 驗證的行為 |
| --- | --- |
| `tests/test_memory_manager.py` | 5 個測試：重啟持久化、scope 隔離、去重、TTL、替代記憶及關係。 |
| `tests/test_retrieval.py` | 6 個測試：embedding 穩定/正規化、相關檢索與分數、向量持久化、scope 隔離、budget 拒絕原因、替代後移除舊向量。 |
| `tests/test_retrieval_boundaries.py` | 4 個測試：不可信索引候選的再驗證、空型別集合、非法評分設定、零權重消融設定。 |
| `tests/test_dataset.py` | 固定資料集有效且涵蓋必要情境。 |
| `tests/test_retrieval_benchmark.py` | 基準能執行全部查詢，結果指標落在合理範圍。 |
| `tests/test_comparison_benchmark.py` | 比較實驗能產出預期報表。 |

目前可數出 18 個測試方法；2026-09-14 強化報告記錄 18 個通過。本次為原始碼導讀，沒有重新執行測試。測試通過不等於已驗證大規模併發、所有儲存故障或真實 LLM 效果。

## 9. 文件與開發技能

| 檔案 | 用途 |
| --- | --- |
| `docs/PROJECT_PLAN.zh-TW.md` | 需求、架構、非功能需求、里程碑與驗收条件；部分 Sprint 狀態落後於程式，需以實作為準。 |
| `docs/QUICKSTART.zh-TW.md` | 本機安裝、操作與驗證的入門指引。 |
| `docs/BENCHMARK_RESULTS.zh-TW.md` | 第一批比較數據、硬體環境、失敗案例與限制；其中 14 個測試是當時的紀錄。 |
| `docs/IMPLEMENTATION_HARDENING.zh-TW.md` | 2026-09-14 的檢索邊界修正、18 個測試與前後 benchmark 紀錄，以及仍待完成的可靠性項目。 |
| `docs/adr/0001-sqlite-as-source-of-truth.md` | 解釋為何 metadata 是事實來源、向量可重建，以及跨儲存一致性的代價。 |
| `docs/adr/0002-provider-agnostic-core.md` | 解釋為何以 Protocol 隔離外部供應商；涵蓋未來 provider 方向，非全部已存在。 |
| `docs/skills/memlite-repo-planner/SKILL.md` | 教開發助手如何先核對程式、測試與 ADR 再規劃。 |
| `docs/skills/memlite-implementation/SKILL.md` | 記憶與檢索實作、除錯與測試的專案工作指引。 |
| `docs/skills/memlite-benchmark-runner/SKILL.md` | 固定條件執行基準、比較與記錄結果的工作指引。 |
| `docs/FILE_GUIDE.zh-TW.md` | 本份逐檔導讀與口試說明。 |

docs/skills 裡的檔案是開發助手使用的指令副本，並非 Agent 執行時的記憶、prompt 或功能模組。

## 10. 本機資料、簡報與工具產物

| 路徑 | 用途 |
| --- | --- |
| `data/.gitkeep` | 保留資料目錄。 |
| `data/demo.db` | 基本記憶管理示範的本機 SQLite 檔。 |
| `data/retrieval-demo.db` | 向量檢索示範的 metadata DB。 |
| `data/retrieval-demo.vectors.db` | 同一示範的向量索引 DB。 |
| `MemLite-Agent-Side-Project-Presentation/outline.md` | 核准的 13 頁數據儀表盤簡報大綱；由草稿複製而來，內文仍有 DRAFT 字樣。 |
| `MemLite-Agent-Side-Project-Presentation/outline.data-dashboard.draft.md` | 保留的數據儀表盤大綱草稿。 |
| `MemLite-Agent-Side-Project-Presentation/PPT_DECISIONS.zh-TW.md` | 講者姓名、展示用途、風格與素材補充等簡報決策。 |
| `MemLite-Agent-Side-Project-Presentation/origin_image/slide_06.png` | 已生成的策略比較頁样稿，是視覺產物，不是實驗數據來源。目錄目前沒有完整 PPTX。 |
| `.git/` | Git 內部版本控制資料，不是專題程式。 |
| `.venv/` | 本機 Python 虛擬環境及工具，不逐一視為自己實作的原始碼。 |
| `memlite_agent.egg-info/` | 套件安裝產生的版本、依賴與入口等 metadata。 |
| `.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/` | 測試、型別檢查與 lint 的工具快取。 |
| 各層 `__pycache__/`、`*.pyc` | Python 執行產生的 bytecode 快取。 |

本次僅盤點 DB 檔的角色，沒有讀取其中私人記憶內容。工具產物依種類說明，未將環境套件與 Git 內部檔逐一列為專題檔案。

## 11. 一次查詢的口試示範

假設先記住「專案主要資料庫是 SQLite」，然後問「主要資料庫是哪個？」：

1. retrieval_cli 將輸入交給 engine。
2. 寫入時 manager 建立 MemoryItem，storage 將原文、來源與狀態存入 metadata DB。
3. engine 使用 deterministic embedding 將內容轉向量，存入 vector DB。
4. 查詢時 RetrievalService 將問題轉向量，vector index 找到相近候選。
5. RetrievalService 回查 metadata，確認 scope、型別、狀態和 TTL，然後計算各項分數。
6. 在結果數與 token budget 內選取，回傳記憶及理由。
7. 目前流程到此結束；未來再由 Prompt Builder 與 LLM adapter 使用選入記憶產生回答。

## 12. 可以主張的成果與下一步

可主張：已完成持久化記憶生命週期、可替換的 provider/index 介面、可解釋混合評分、預算篩選、邊界驗證、固定資料集與受控比較的初版。

尚未完成：exact/semantic response cache、LRU/LFU 容量淘汰、摘要壓縮、自動記憶分類或層級搬移、真實語意 embedding、LLM/Agent loop、API/UI、部署與完整簡報。TTL 目前是過期篩選，不會自動實體清除資料。

向教授介紹時，建議依 models -> manager -> storage -> engine -> embedding/vector -> retrieval -> evaluation -> tests 的順序走讀。先說明資料與生命週期，再說明選取決策，最後用可重現實驗支持主張。
