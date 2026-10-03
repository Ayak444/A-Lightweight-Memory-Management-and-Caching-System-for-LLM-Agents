# MemLite-Agent 數據儀表盤簡報大綱

> Status: DRAFT，等待大綱確認  
> 作者：陳格洋  
> 格式：13 頁，16:9，適合 GitHub 自行閱讀  
> 語言：繁體中文，保留必要英文技術名詞  
> 指定風格：深色、清爽、專業的數據儀表盤風  
> 數據來源：`../experiments/results/current/`  
> 數據限制：10 queries、deterministic lexical embedding、本機 exact vector scan

## Slide 1：MemLite-Agent

**版面角色：** 封面／產品定義

**重點：**

- Lightweight Hierarchical Memory and Semantic Cache for LLM Agents。
- 將 Agent 記憶變成可查看、可替換、可評估的外部狀態。
- 作者：陳格洋。
- Side project 定位：工程作品集 + 可重現實驗。

**視覺構想：** 深炭黑背景，中央是 Agent → Memory Manager → LLM 的簡潔資料流；右下角用小型 KPI 標籤預告「14 tests / 10 queries / 5 strategies」。

**必要來源圖片：** 無。

## Slide 2：Prototype Dashboard

**版面角色：** Executive dashboard／結果先行

**重點：**

- Best current configuration：Hybrid top-1。
- Pass Rate 80%、Precision 0.80、Recall 0.80、MRR 0.80。
- 平均選入 9.2 estimated tokens。
- 本地 retrieval p50 0.754 ms、p95 0.845 ms。
- 所有數字皆來自 deterministic offline baseline，不代表 production LLM 表現。

**視覺構想：** 上方四張 KPI cards；中央放 top-1 與 top-5 的比較條；底部放醒目的 baseline 限制標籤。

**必要來源資料：** `strategy_comparison.csv`，數值為 strict input，不可改寫。

**必要來源圖片：** 無。

## Slide 3：為什麼需要 Memory Manager？

**版面角色：** 問題／動機

**重點：**

- Conversation history 持續增加 context token、等待時間與成本。
- 相似任務重複呼叫 LLM，缺少安全的重用機制。
- Naive vector retrieval 可能選入看似相關但實際無用的內容。
- 過期與衝突記憶可能悄悄改變後續答案。
- 大學生動機：希望從底層理解記憶決策，而不只串接現成 Agent framework。

**視覺構想：** 左側是持續膨脹的 context 曲線，右側是三個風險狀態卡：Cost、Latency、Pollution。

**必要來源圖片：** 無。

## Slide 4：設計主張與系統架構

**版面角色：** Architecture／solution overview

**重點：**

- Working、Episodic、Semantic Memory 分開管理。
- SQLite 是 source of truth；vector index 可重建。
- Retrieval、compression、eviction 與 cache 是可替換 policy。
- Prompt Builder 在 LLM 呼叫前執行最終 token budget。
- 所有 retrieval 保留候選、分數與拒絕原因。

**視覺構想：** 左側架構圖，右側四張原則卡：Hierarchical、Inspectable、Policy-driven、Measurable。

**必要來源圖片：** 無，依已確認的程式架構生成。

## Slide 5：Benchmark 怎麼量？

**版面角色：** Methodology dashboard

**重點：**

- Dataset v1.0.0：10 sequences / 10 queries。
- 7 類場景：repetition、long horizon、preference、update、conflict、irrelevant、scope isolation。
- 比較 5 種 retrieval 策略、6 種 token budget、5 種 corpus size。
- 主要指標：Pass Rate、Precision、Recall、MRR、Token、p50/p95 latency。
- 環境：Ryzen 7 7800X3D、31.1 GB、Windows 11、Python 3.11.9。

**視覺構想：** 中央實驗矩陣；周圍放 dataset、策略、budget、scale 四組摘要卡。

**必要來源資料：** `comparison.json` 與 benchmark 報告中的執行環境。

**必要來源圖片：** 無。

## Slide 6：Retrieval Strategy Comparison

**版面角色：** 核心比較／bar chart + KPI

**重點：**

- Similarity top-5、Hybrid top-5、Hybrid top-3 都是 70% Pass Rate。
- Hybrid top-1 提升到 80%，Precision 由 0.60 提升至 0.80。
- Top-1 平均選入 token 由 12.7 降到 9.2，下降約 27.6%。
- Strict threshold 0.20 只剩 50% Pass Rate 與 0.50 Recall。
- 結論：目前資料集的主要問題不是候選不足，而是選入過多與過度閾值化。

**視覺構想：** 分組長條圖比較 Pass/Precision/Recall；右側 insight card 強調「Top-1：+10pp pass rate，-27.6% token」。

**必要來源資料：** `strategy_comparison.csv`，所有圖表數值為 strict input。

**必要來源圖片：** 無。

## Slide 7：Token Budget Trade-off

**版面角色：** Trade-off／line chart + comparison

**重點：**

- Budget 8：Pass Rate 與 Recall 都只有 40%。
- Budget 16：Pass Rate 70%、Precision 0.70、Recall 0.80。
- Budget 32 到 500：Pass Rate 不再增加，Precision 反而降為 0.60。
- Budget 16 相較 32 平均少用約 15.0% token。
- 結論：更大的 context budget 不必然帶來更好的 retrieval quality。

**視覺構想：** 雙軸折線展示 budget 對 Pass Rate/Recall 與實際 token；16 token 位置使用藍綠高亮。

**必要來源資料：** `token_budget_comparison.csv`，所有圖表數值為 strict input。

**必要來源圖片：** 無。

## Slide 8：Corpus Size vs. Latency

**版面角色：** Scalability／latency curve

**重點：**

- 10 筆：p95 1.227 ms。
- 100 筆：p95 4.702 ms。
- 500 筆：p95 28.658 ms。
- 1,000 筆：p95 55.383 ms；2,000 筆：p95 99.992 ms。
- Exact scan 近似線性成長，2,000 筆已到 MVP 100 ms 目標邊界。

**視覺構想：** 大型 latency curve，100 ms 位置畫目標線；右側以狀態卡標出 Local MVP 合格、Scale-up 需要 ANN backend。

**必要來源資料：** `corpus_latency_comparison.csv`，所有圖表數值為 strict input。

**必要來源圖片：** 無。

## Slide 9：三個失敗案例比平均分更重要

**版面角色：** Failure analysis／diagnostic dashboard

**重點：**

- Long horizon ×2：查詢和記憶沒有足夠共同詞彙，lexical embedding 無法理解語意。
- Conflict ×1：正確記憶排名第一，但污染記憶仍進入 context。
- 0.20 strict threshold 降低雜訊，也讓 Recall 從 0.80 掉到 0.50。
- 下一個 ablation：real embedding、pollution gate、reranker。
- 不把目前 80% Pass Rate 包裝成最終效果。

**視覺構想：** 三張 failure cards，各自顯示 symptom、root cause、next experiment；橙紅只用在錯誤狀態。

**必要來源資料：** `docs/BENCHMARK_RESULTS.zh-TW.md` 的失敗案例表。

**必要來源圖片：** 無。

## Slide 10：Semantic Cache 的下一組比較

**版面角色：** System design／planned experiment

**重點：**

- Exact hit 處理完全相同的 request。
- Semantic hit 處理同義改寫，但仍需 scope validation。
- Fingerprint 包含 prompt、model、tool schema 與 relevant context version。
- 比較 Cache Hit Rate、Rejected Hit Rate、Latency 與 estimated cost saving。
- 本頁是下一階段設計，不展示尚未量測的假數據。

**視覺構想：** Cache decision funnel：Exact → Semantic candidate → Fingerprint → Hit/Reject/Miss；右側 KPI 使用 `Pending` 而非數字。

**必要來源圖片：** 無。

## Slide 11：Engineering Quality Dashboard

**版面角色：** 工程品質／status dashboard

**重點：**

- 14 tests passed。
- Ruff lint passed；Ruff format passed。
- Strict mypy passed。
- 10/10 benchmark sequences 通過 schema validation。
- SQLite/vector persistence、scope、TTL、supersede、token budget 都有測試覆蓋。

**視覺構想：** CI status rows 搭配四張綠色狀態卡，下方用小型 coverage map 表示已測模組，不虛構 coverage 百分比。

**必要來源資料：** 本次實際 test/lint/type-check 輸出。

**必要來源圖片：** 無。

## Slide 12：目前完成與下一步

**版面角色：** Roadmap／delivery status

**重點：**

- 已完成：memory lifecycle、SQLite、deterministic embedding、persistent vector index、retrieval trace、benchmark matrix。
- 下一步：semantic cache 與 pollution rejection gate。
- 再下一步：real embedding + Chroma、LLM adapter、FastAPI、UI。
- 最後：擴充至至少 50 sequences，加入實際 token/cost/task success。
- 技術原則：一次只打通一個可驗收的 vertical slice。

**視覺構想：** 橫向 milestone progress，Completed、Active、Planned 三種狀態；不要使用虛構完成百分比。

**必要來源圖片：** 無。

## Slide 13：目前可以證明什麼？

**版面角色：** Summary／closing dashboard

**重點：**

- 輕量化、可解釋的 memory retrieval 已經可以端到端執行。
- 在目前小型資料集上，top-1 比 top-5 更準且使用更少 context。
- Budget 16 是目前資料分布的有效 sweet spot，但需要更大資料集驗證。
- Exact scan 到 2,000 筆時接近 100 ms p95，支持下一階段導入 ANN backend。
- 最重要成果：建立了一條能用真實數據反覆比較策略的實驗管線。

**視覺構想：** 中央 conclusion card，周圍四個 evidence chips：Quality、Context、Latency、Reproducibility；底部標示 `Next: Semantic Cache Experiment`。

**必要來源圖片：** 無。

---

## 數據使用規則

- 投影片只使用 `experiments/results/current/` 與 `docs/BENCHMARK_RESULTS.zh-TW.md` 中的數字。
- 圖表中的軸、數值與策略名稱不可由圖片模型自行補值。
- 所有 latency 都標示為 local retrieval，排除 remote embedding 與 LLM。
- 所有 quality metrics 都標示樣本數 `n=10 queries`。
- 尚未實作的 Semantic Cache 指標一律顯示 `Pending`，不使用估計節省比例。

## 視覺方向紀錄

- 深炭黑或深灰背景，不使用壓迫的純黑監控牆。
- 主要數據使用清晰藍色與青綠色；比較組使用柔和紫色。
- 綠色只表示通過，橙色表示注意，紅色只表示失敗或風險。
- KPI 使用大型 tabular numerals；中文標籤必須清楚可讀。
- 使用細邊框、低強度陰影、折線圖、長條圖、status dots 與少量 sparkline。
- 各頁版型依內容角色變化，不連續重複同一組 KPI 卡排列。

## Approval Gate

請確認：

- 是否接受 13 頁以及 Slide 2 結果先行的敘事。
- 是否接受以 `Hybrid top-1`、`Token budget 16`、`2,000 memories ≈ 100 ms p95` 作為三個主要 insight。
- 是否保留 Slide 10「Semantic Cache 下一組比較」，即使目前數據仍是 Pending。
- 是否接受深色改編版數據儀表盤風。

目前尚未建立 `deck_spec.json`、prompt jobs、slide images、speaker notes 或 PPTX。

