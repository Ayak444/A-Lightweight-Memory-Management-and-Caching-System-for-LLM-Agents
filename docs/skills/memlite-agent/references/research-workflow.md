# 接續研究

進度入口：`PROGRESS.md`。研究總結：`docs/BENCHMARK_RESULTS.zh-TW.md`、`docs/RESEARCH_UPDATE_20261003.zh-TW.md`、`docs/CHALLENGE_RESULTS_20261003.zh-TW.md`。核心 facade：`memlite/engine.py`；檢索：`policies/retrieval.py`；淘汰：`policies/eviction.py`；控制實驗：`evaluation/challenge_benchmark.py`。

最新研究請依 PROGRESS 連結閱讀，包含重要性保護與壓縮預算實驗。下載安裝與 public 前驗收見 repo 的 `docs/SKILL_USAGE.zh-TW.md`、`docs/RELEASE_CHECKLIST.zh-TW.md`。這些路徑相對於 runtime checkout，不是 skill 的安裝位置。

Agent 的 `auto_extract` 是需明確選用的關鍵字規則，不代表抽出的 LLM 句子已被驗證為事實。它可能保存錯誤、矛盾或敏感內容；未取得持久化授權時保持關閉，研究時使用獨立資料庫。L3 的成功回傳用量包含摘要與主回答，`metadata.provider_calls` 分階段記錄模型、token 與延遲；不要把 API 的 process-local 輸入估計配額當成真實費用上限。失敗的 provider 呼叫需另以實驗紀錄及 provider 用量核對，不能從沒有成功回傳推論零費用。

## 可重現命令

以下命令從 repo 根目錄執行；其他平台移除 Windows 環境路徑，改用選定 Python。遵守當前 workspace 的命令工具指示。

```powershell
rtk proxy .venv-research/Scripts/python.exe -m pytest -q
rtk proxy .venv-research/Scripts/python.exe -m ruff check .
rtk proxy .venv-research/Scripts/python.exe -m ruff format --check .
rtk proxy .venv-research/Scripts/python.exe -m mypy memlite
rtk proxy .venv-research/Scripts/python.exe -m memlite.evaluation.challenge_benchmark --dataset experiments/datasets/challenge.json --output experiments/results/new-challenge-run --repeats 3
rtk proxy .venv-research/Scripts/python.exe -m memlite.evaluation.protection_benchmark --output experiments/results/new-protection-run --repeats 3
rtk proxy .venv-research/Scripts/python.exe -m memlite.evaluation.compression_benchmark --output experiments/results/new-compression-run --repeats 3
rtk proxy .venv-research/Scripts/python.exe -m experiments.run_comparisons --dataset experiments/datasets/mvp.json --output experiments/results/new-mvp-run
```

使用新的 output 目錄，保留舊證據。challenge.json 是已固定版本的 synthetic 資料，不需再次 `--create-dataset`。固定時間、ID、初始存取次數與最後存取時間，每個策略／案例／重複從獨立資料庫開始；不要以睡眠或實際存取累積代替初始條件。

## 解讀界線

- 固定 top-1/top-3、候選數 20、budget 500，以及 LRU/LFU/TTL/hybrid 與 capacity 2/4/8；實驗後修改規則必須記錄新版本，重新評估而不是覆蓋結果。
- development/evaluation 以不同 project 詞彙與 scope 分開，但共用模板，因此不能視為獨立真實 held-out validation。這些案例刻意是壓力測試，不代表實際使用分布。
- repeated selection stability 只驗證可重現；同一題重跑三次不能說樣本量增加三倍。
- precision、pollution_fraction 為逐 query macro 平均；空結果均設為 0，另看 recall 與 forbidden_hit，避免空檢索看似零污染就被誤判為最佳。
- pass 要求所有 expected 被選入、沒有 forbidden；不是 LLM 任務完成率。Token 是 UTF-8 bytes/4 向上取整估計，不是 provider usage。
- 抽取式壓縮可透過 `PromptBuilder(memory_token_budget=...)` 選用；原始記憶不變。壓縮實驗只驗證實際 Agent prompt 的必要事實字串保留，不是 fake 回覆品質，不能以此完成 RQ4 的真實回答驗收。
- 新增真實 provider 或 compression 研究時，先訂問題、baseline、任務與品質判準，再確認費用／額度／資料隱私授權。

每輪記錄變更、執行時間與版本、資料雜湊、策略、逐題失敗、結果及限制，更新 PROGRESS，不將「程式存在」等同「研究已完成」。
