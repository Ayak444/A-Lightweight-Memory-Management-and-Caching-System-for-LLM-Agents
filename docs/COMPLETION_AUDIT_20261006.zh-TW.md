# 專案完成度與錯誤審查

日期：2026-10-06（Asia/Taipei）。檢查目前工作目錄，不是只看已提交版本。這輪沒有修改功能程式、同步個人 skill、push、公開 repo 或呼叫付費 API。

## 結論

**尚未全部完成。** 本地核心與 skill 的基礎能力已有可用實作，但進度表、驗收清單、README 與發行檔不是同一版本；既有測試通過，也不代表新功能沒有缺陷。

GitHub 發布本地研究原型、完整研究驗收，以及公開 API 是三個不同目標。只發布清楚標示限制的本地 skill，不一定需要先部署公開 API；但若沿用 PROGRESS 中完整專案的完成條件，下面的研究與展示項目仍不能勾選完成。

## 已重現的問題

### 1. 程式品質檢查失敗，現有 CI 會被阻擋

Ruff check 有 8 個錯誤，包含 AgentLoop 的過長行、`tests/test_prompt_builder.py` 的 imports 與過長行。format check 有 5 個檔案不符合格式：AgentLoop、API、AgentLoop 測試、API 測試與 PromptBuilder 測試。

[CI 定義](../.github/workflows/tests.yml) 在 pytest 與封裝前先執行這些檢查，因此目前不能把「全部檢查通過」作為最新狀態。mypy 通過不會替代 lint／format。

### 2. 快取命中會跳過要求的自動記憶抽取

位置：[AgentLoop](../memlite/agent/loop.py)，第 88 行直接回傳，第 113 行才執行抽取。

離線重現：先以 `auto_extract=False` 問問題產生快取，再對同題、同 scope 開啟 `auto_extract=True`；第二次確實命中快取，但仍有 0 筆記憶。相同回答在全新 scope 開啟抽取時則產生 1 筆記憶。

使用者要求的副作用不應因回答是否已被快取而改變。修正時需決定在 cache hit 路徑執行抽取，或將有寫入副作用的請求排除快取，並補上切換開關的回歸測試。這不是自動抽取品質已驗證的證據。

### 3. L3 在快取查詢前呼叫摘要，而且漏記摘要用量

位置：[AgentLoop](../memlite/agent/loop.py) 第 64 行建立 prompt，第 83 行才查快取；[PromptBuilder](../memlite/agent/prompt_builder.py) 第 58 行呼叫摘要。

使用完全離線的 recorder：第一次問題共 2 次 provider 呼叫（摘要＋主回答），第二次明確命中快取仍額外呼叫一次摘要，累計 3 次。摘要會消耗 API 資源，不能將 cache hit 宣稱為「完全沒有 provider 呼叫」。

recorder 刻意回傳固定用量：首次兩次呼叫合計 32，Agent 回傳的 total_tokens 卻只有主回答的 10；摘要結果用量沒有被保存或彙總。這些是模擬用量，用於驗證漏記路徑，不是真實 API 數據。[PROJECT_GUIDE](../PROJECT_GUIDE.md) 第 411 行要求 L3 的額外 token、latency、cost 獨立記錄，目前尚未符合。

摘要 request 的 model 為空字串，而主回答是呼叫者指定的 model；如果設計上需要不同摘要模型，應有明確設定與記錄，而不是讓成本評估假設兩者一致。

### 4. 無效 query 會先扣預算，再回傳錯誤

位置：[API](../memlite/api/main.py)，第 317 行扣預算，第 321 行才驗證／檢索。

離線 TestClient 重現：將上限設為 1，空白 query 回傳 400，卻已扣 1；緊接著原本符合上限的有效 query 被回傳 429。若預算代表有效工作或模型用量，需要先驗證、或在失敗時回滾；若要限制包括失敗嘗試的輸入量，需清楚定義這是不同的配額。

此外，現有計數是 UTF-8 bytes/4 的輸入估計，儲存在 process-local dict，不是實際 Agent／摘要／embedding 的費用上限。寫入記憶不經此配額，reset 不需授權。這不能取代公開服務的帳號授權、持久化用量與實際成本控制。

### 5. L3 缺少 provider 時會默默略過壓縮

位置：[PromptBuilder](../memlite/agent/prompt_builder.py)，第 57 行。

直接使用 `PromptBuilder(memory_token_budget=8, compression_strategy="abstractive")` 建立訊息，沒有提供 provider 時不會拒絕配置或回報壓縮未執行；重現中 20 句背景內容全部保留，超出要求的預算。AgentLoop 會注入 provider，因此這個案例主要影響獨立使用 PromptBuilder 的呼叫者。需明確驗證配置或定義安全的 fallback，避免讓使用者以為已套用預算。

## 完成度與文件落差

| 項目 | 核對結果 |
| --- | --- |
| M2 壓縮與快取 | L3 路徑與 mock 測試存在，但新副作用、用量追蹤與真實品質未驗收；不能以程式存在代表全部完成 |
| M3 Evaluation | 既有離線比較可用；RQ1／RQ2／RQ4 真實回答品質、成本與獨立資料仍缺證據，與 milestone 的「完成」不一致 |
| M4 展示 | `docs/demo_output.txt` 不是 GIF 或截圖；UTF-8 讀取有 367 個替代字元，中文已損壞 |
| 簡報 | 資料夾目前只有 outline、PPT decisions 與 `slide_06.png`；沒有完整 PPTX |
| 公開前清單 | private CI、GitHub 安裝、歷史／素材檢查、Release、訪客下載驗收仍未勾選 |
| Docker | 目前 PATH 找不到 docker，未完成容器 build、health、持久化、重啟驗收 |
| 發行 wheel | `dist/runtime/memlite_agent-0.1.0-py3-none-any.whl` 不含最新 auto_extract、L3 strategy 或 TOKEN_BUDGET_CAP；須在修正後重新建置 |
| 個人安裝 skill | 本機已安裝 SKILL.md 第 25 行仍說 TTL 修正未實作；與 repo runtime 不一致，須比較後更新，不要默默覆蓋 |
| 文件與測試數 | PROGRESS／README 仍寫 120；目前實際為 125。Release checklist 與研究報告也尚未反映新增的 L3／抽取／配額路徑 |

獨立資料、人工品質 rubric、明確來源／版本的矛盾案例與抽取污染評估，仍是研究待辦。公開多租戶 API 另需登入、scope 授權與可追蹤成本；scope 字串隔離不是帳號驗證。

## 本輪驗證

| 檢查 | 結果 |
| --- | --- |
| pytest | 125 passed、62 subtests passed，76.57 秒 |
| Ruff check | 失敗，8 個錯誤 |
| Ruff format --check | 失敗，5 個檔案需格式化 |
| strict mypy memlite | 通過，44 source files |
| repo skill quick_validate | 通過 |
| diff whitespace | 通過，但不涵蓋未追蹤檔案；不能用來取代 Ruff |
| 新功能重現 | 全部使用 recorder／TestClient 與臨時資料庫，無外部 API 呼叫 |

初次測試受沙箱限制：預設 TEMP 無法開啟 SQLite；本地 API 的 Windows asyncio socketpair 也卡住。先將 TEMP/TMP 改到專案內 `dist/review-temp-20261006/`，再經工具批准於沙箱外跑完整離線測試後通過。因此未把環境錯誤算成產品邏輯失敗，也未假裝初次驗證成功。

重現腳本在本機 `experiments/results/audit-20261006/reproduce.py`，依現有 ignore 規則不發布。它不修改 live 記憶，只對自己建立的臨時資料庫操作。模擬用量不能用於真實成本宣稱。

## 建議順序

1. 修正快取／抽取副作用、L3 用量與配額處理，為上述案例補正式回歸測試。
2. 修正 lint／format，再核對最新測試數與 milestone 狀態；保留已完成的實作，不以未驗證項目假裝全部完成。
3. 修正 demo 編碼、完成展示素材，重建 wheel／skill 發行檔並同步使用文件。
4. 凍結獨立任務與品質 rubric，再經模型、費用上限與資料傳送授權完成真實模型評測。
5. 保持 private，完成遠端 CI、乾淨 GitHub 安裝與發行前檢查；由使用者最後決定轉 public。

如果目標改為「只發布離線研究版 skill」，應明確縮小完成範圍並保留研究限制，無需把公開網站／API 部署強行當成 skill 安裝的必要條件。
