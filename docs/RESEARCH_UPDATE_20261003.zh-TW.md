# 2026-10-03 研究與整合驗證

## 本輪目標

接續 PROGRESS.md 內已存在的 Agent、cache、compression、API 與 evaluation 程式，將「有程式檔案」提升為「可跑、可驗證、可重現」。本輪未呼叫付費 LLM 或 embedding API。

原始檢查發現：46 個測試中 3 個失敗；新增 Agent 回歸測試在原實作上另重現 6 個問題。舊 .venv 指向失效的 Python 安裝，因此另建 .venv-research，使用 Python 3.12.14 驗證。

## 實作與修正

- PromptBuilder 使用 RetrievalResponse.candidates，將選入記憶送進 provider。
- Agent 快取指紋包含 model、system prompt version、實際指令、對話歷史、選入記憶內容與 tool schema version。指紋不含當前問題，保留同義查詢重用的可能。
- 只有 CacheEventType.HIT 可以回傳 cached response；rejected_hit 不當成成功命中。命中結果的 provider token usage 為零。
- 透過 Engine 新增、替代、刪除與淘汰記憶後，保守地失效同 scope 快取。「remember／記住」指令繞過 response cache，確保寫入行為被執行。
- Cache 重新驗證來源 scope、跳過非有限相似度；遇到不同 context 的候選後繼續找相符候選。拒絕非正 TTL。
- Extractive compression 不再強制塞入超預算第一句，計算合併後文字的估算 token；L3 摘要超預算或空白會顯式失敗。尚無真實摘要品質實驗。
- API 修正 stats／lookup 欄位、context mismatch 行為與空型別篩選，提供 context 指紋欄位；非法 type／TTL 回傳 client error，health 不受示範 rate limit 阻擋。
- 六步 fake-provider demo 可完成；fake provider 回覆只是確認訊息，不代表能作出向量資料庫推薦。
- B0/B1 改為原始 memory-write history，保留 superseded facts。B1 在同 scope 中取最近 10 次寫入，再依 budget 選取；並非以 recency weighting 模擬歷史。
- 比較 runner 實際接上 runs.db、environment.json 與 summary.md，記錄策略配置、候選 trace、指標與 dataset SHA-256。延遲不含 trace 持久化時間。

## 重現命令

在 repo 根目錄使用可用的 Python 3.11+ 環境；本輪使用獨立的 .venv-research。一般環境先安裝 `python -m pip install -e ".[dev]"`。

```powershell
.venv-research/Scripts/python.exe -m pytest -q
.venv-research/Scripts/python.exe -m ruff check memlite tests experiments
.venv-research/Scripts/python.exe -m ruff format --check memlite tests experiments
.venv-research/Scripts/python.exe -m mypy memlite
.venv-research/Scripts/python.exe -m memlite.demo
.venv-research/Scripts/python.exe -m experiments.run_comparisons --output experiments/results/research-20261003
```

從未安裝套件的環境執行時，`-m experiments.run_comparisons` 可確保 repo 根目錄可被 Python 找到。

驗證：68 tests passed，8 subtests passed；Ruff 通過、55 個 Python 檔案格式通過、mypy 40 個來源檔案通過。14 個測試檔涵蓋 lifecycle、retrieval、cache、eviction、providers、compression、API、agent 與 experiment artifacts。

## 實測結果

原始輸出：`experiments/results/research-20261003/`。舊 current 結果未覆蓋。dataset version 2.0.0，31 sequences／31 queries，deterministic lexical embedding，local SQLite exact scan。

| 策略 | Retrieval pass | Precision | Recall | 平均選入估算 tokens |
| --- | ---: | ---: | ---: | ---: |
| B0 full history | 70.97% | 0.4941 | 1.0000 | 27.42 |
| B1 recent window | 70.97% | 0.4941 | 1.0000 | 27.42 |
| Similarity Top-5 | 80.65% | 0.7016 | 0.9355 | 17.68 |
| Hybrid Top-5 | 80.65% | 0.7016 | 0.9355 | 17.68 |
| Hybrid Top-3 | 80.65% | 0.7043 | 0.9355 | 17.26 |
| Hybrid Top-1 | 93.55% | 0.9355 | 0.9355 | 11.77 |
| Hybrid Top-3 strict | 54.84% | 0.5484 | 0.6129 | 8.48 |

Hybrid Top-1 在此資料集通過 29/31，較 B0 的 22/31 高；選入記憶估算 token 約少 57.06%。這是檢索約束通過率與 memory context 大小，不是 LLM 回答成功率或付費 API token。

目前每題只有一個主要 expected memory，這偏向 Top-1。31 題中的每個 scope 歷史均短於 10 筆，所以 B0/B1 實測相同；另有超過視窗的合成回歸測試驗證 B1 確實會丟棄較早事件。研究上仍需加入長歷史、多個 relevant memory 與多輪案例。

Token Budget 16 的 pass 為 70.97%，32 為 80.65%；擴充後已不支持舊 10 題報告中「16 與 32 通過率相同」的結論。Dataset 版本不同，不把新舊通過率差異歸因於本輪修正。

2,000 筆語料的本輪 P50 為 76.07 ms、P95 為 80.22 ms（30 runs）。基準採本機 exact scan，不含遠端 embedding 或 LLM；單次量測不用於主張相對舊機器環境的效能提升。

### 重複任務快取比較

6 個 query 各自使用獨立 scope、重複 5 次；context 不變。比較有 cache 與無 cache 的同一批 30 個任務。

| 項目 | 無快取 | 有快取 |
| --- | ---: | ---: |
| Provider calls | 30 | 6 |
| Cache hits | 0 | 24 |
| Cache hit rate | 0% | 80% |
| Fake-provider estimated tokens | 860 | 172 |
| 相同任務輸出一致率 | 100% | 100% |
| 本機 end-to-end P50 ms | 0.048 | 1.157 |

此實驗支持「重複任務避免 24 次 provider 呼叫」，不支持真實語意改寫品質、回答正確率或實際金額節省。fake provider 幾乎沒有生成成本，因此 SQLite lookup／write 讓快取版本本機延遲較高；真實 provider 的延遲效益仍待量測。

### 預設 Hybrid Top-5 失敗案例

| 案例 | 實測結果 | 解讀 |
| --- | --- | --- |
| long-horizon-001 | 選 deploy，漏 source_of_truth | lexical embedding 無法充分連結改寫的事實來源問題。 |
| long-horizon-002 | 沒有選入 non_goal | 詞彙差異與門檻造成漏取。 |
| conflict-001 至 conflict-004 | 正確記憶與 forbidden memory 一起選入 | pollution penalty 影響排序，但目前沒有自動矛盾判定或單獨 pollution gate。 |

完整歷史基準保留所有事實，包括舊事實與污染內容；因此 Recall 為 1，pass 仍可能失敗。

## 仍待完成的研究與展示

1. 研究資料集：建立明確 train／held-out 分割、長歷史、多筆 relevant memory 與無相關記憶案例，記錄逐題 trace。禁止以移除失敗題提升分數。
2. RQ1／RQ2：真實 provider 加固定答案檢查器，量測回答品質、token usage、網路延遲與明確費率下的成本；先從少量受控案例開始。
3. RQ3：固定存取歷史、容量與 TTL，執行 TTL/LRU/LFU/hybrid 的污染率與 recall 消融實驗。政策程式已有，controlled comparison 尚未加入。
4. RQ4：比較 L1/L2/L3 的壓縮率、事實保存與回答品質；目前只有功能及 budget 邊界測試。
5. 可靠性：metadata/vector 寫入失敗追蹤、cache 索引修復、候選補取、過期 cache 清理與失效統計定義。
6. 展示／發布：UI、真實截圖、完整 PPT、公開部署與驗證仍待完成。API 是本機研究展示介面，尚未提供使用者驗證與 scope 授權。

新增 CI 定義可在 GitHub push/PR 時執行 Python 3.11/3.12 品質檢查；本輪沒有 push，也沒有 GitHub Actions 執行結果。
