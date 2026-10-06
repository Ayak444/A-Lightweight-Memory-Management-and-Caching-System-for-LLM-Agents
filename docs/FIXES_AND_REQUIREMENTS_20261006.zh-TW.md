# 錯誤修正與完成剩餘工作的條件

更新：2026-10-06。前次審查為 [COMPLETION_AUDIT](COMPLETION_AUDIT_20261006.zh-TW.md)，保留作為修正前的歷史證據，不覆寫原來的問題紀錄。

## 本輪已修正

- cache hit 仍會執行使用者明確選用的 `auto_extract`，保留 scope、來源與 confidence 0.7；預設不抽取。
- L3 先以原始 selected context、摘要模型與預算核對快取，命中後不再先呼叫摘要。L2 仍以實際壓縮 context 核對，避免忽略 query 導致的選句差異。
- 成功回傳用量加總摘要與主回答，另在 `metadata.provider_calls` 分階段記錄模型、requested_model、token 與 provider 延遲。不修改 provider 原本的 result 物件。
- 摘要模型可明確設定；未設定時 Agent 沿用指定主模型。standalone builder 缺少摘要 provider 或策略拼錯會拒絕，不默默略過壓縮。
- API 無效輸入不扣配額，失敗的 cache／retrieval 操作退回 reservation；超過上限不再扣款。配額明確標記為 process-local 的 estimated input tokens，不是真實成本上限。
- 修正 Ruff／格式；demo 改為由程式直接寫 UTF-8、拒絕無授權覆蓋並清理自己的臨時資料庫。匯出檔不包含本機暫存目錄的實際路徑。
- 新增 8 個 Agent accounting／快取回歸測試、4 個 API 配額測試與 1 個 demo 匯出測試。pytest：138 tests、62 subtests 通過；unittest：138 tests 通過。
- 本機 skill 已先備份再同步八個檔案，其他技能與 metadata policy 不變。

尚未量測真實模型；所有新回歸案例都使用 recorder／fake provider。provider 失敗、timeout 或 usage 缺失時不能從沒有成功回傳推論零費用，後續實驗需獨立記錄失敗並與供應商 usage 對帳。

## 1. 真實模型、用量／成本與獨立資料

**仍缺的工作**：凍結任務、baseline、固定參數與品質 rubric；建立 runner，保存原始 prompt／回答、usage、分階段延遲、失敗與成本；用真正的 embedding／LLM 或本地模型量測，而不是把 lexical retrieval pass 當作答案成功率。

**需要你提供／決定**：

- 主模型、摘要模型與 embedding 模型名稱；選外部 API 或本地模型。
- 外部 API 的憑證在本機 `.env` 或安全的環境變數準備，不貼到對話／Git；本地模型則需可用模型與執行環境。
- 單次與累計費用上限、最多呼叫數、重試上限；是否允許將指定資料送到模型服務。未授權前只跑離線驗證。
- 可使用的去識別化任務／文件，或同意使用另外撰寫的 synthetic 任務；保留一組不參與調參的獨立 evaluation 集合。
- 人工答案與判分規則的確認者。可用預先確認的 expected facts／rubric，但不能讓調參後的同一批題目假裝 held-out。

**完成證據**：品質、token／成本、端到端 latency 的配對表；必要事實／污染錯誤與失敗分析；模型與價格版本、資料 hash、環境及逐題紀錄。不同模型費用分開計算，價格在執行時核對，不先填假數字。

這些設計與 runner 可以接續實作，不一定需要你提供現成 dataset；真正評估、資料外傳與費用則須先有上述條件。

## 2. 衝突治理與抽取污染

**仍缺的工作**：明確的來源／版本／有效時間、相互矛盾的案例、待確認記憶與人工接受／拒絕機制；比較不抽取、關鍵字抽取、來源確認等條件，量測錯誤寫入、過期資訊、矛盾與跨 scope 污染。

**需要的資料與決策**：哪些來源可視為已確認、誰確認新事實、矛盾時保留待審或 supersede 的規則，以及不得保存的資訊種類。可先用人工撰寫的假事實與預先標記真偽，不需使用你的私人對話或真實秘密。

**完成證據**：ground truth 與來源可追蹤的案例、錯誤抽取率／衝突檢出率／誤拒率、逐條 accepted/rejected trace。高 confidence 不能直接代表真實性；目前的 heuristic 不算已完成治理。

## 3. PPT、GIF／截圖

**已完成**：`docs/demo_output.txt` 的中文編碼修復；它仍是文字紀錄，不是 GIF 或截圖。

**仍缺的工作**：完整 deck、圖表、圖像與排版驗收，以及實際可重播的 30–60 秒 demo 素材。現有 outline 和單張 slide 不能代表完整 PPTX。

**不必重新提供**：姓名陳格洋、繁體中文、深色清爽專業風與數據儀表盤風格，已知且可沿用。

**還需要確定**：簡報是呈現「離線研究原型」或包含尚待評估的真實模型結果；展示用 CLI 或未來 UI。現有 synthetic 數據可以先做 deck，但標籤必須清楚，不能說已證明真實任務成功或 API 省費。

**完成證據**：可開啟的完整 PPTX、逐頁預覽與視覺檢查、可觀看的完整 demo。圖片生成／錄影工具若涉及外部服務或成本，需另確認範圍。

## 4. wheel、本機 skill 與文件

**本輪處理範圍**：重建包含新修正的 wheel／skill ZIP，以新環境隔離匯入驗證，不靠 editable checkout；個人 skill 先備份再同步。舊 dated 產物保留作歷史，不刪掉或覆蓋其他人的檔案。

**最後發行仍需**：決定正式版本／tag、重新核對 checksum 與安裝文件、在乾淨機器取得全部第三方依賴並走完教學。無依賴 smoke 只驗證離線核心，不代表 API／OpenAI adapter 全部環境都驗收成功。

目前維持開發版本 0.1.0，以 dated 輸出目錄區分修正快照，不假裝已發布新正式版本。建置成功，但 Setuptools 對既有 TOML license table 發出 deprecation warning；正式發行前可遷移 SPDX 並設定相容的 build-backend 下限。本輪未為消除警告而無關升級依賴。

## 5. GitHub CI、Release 與公開前檢查

**需要你提供的權限／決策**：GitHub 存取權、確認哪些 staged／unstaged／untracked 檔案允許提交，並明確授權 private push 與建立 Release。現在工作目錄有既有修改，不會擅自把全部檔案 commit 或 push。

**仍缺的工作**：private repo 上執行 CI、測試下載 artifact、乾淨 clone 安裝、檢查整個待公開 Git 歷史與素材授權、上傳版本檔及 checksum、最後訪客下載驗收。

MIT LICENSE 已有，但不代表依賴、圖片或所有歷史檔案都已檢查。需要保留素材來源與授權紀錄，不把 API key／個資放到歷史中。只有你確認條件成立後才轉 public；目前不更改 visibility。

## 6. Docker 與公開 API

**環境條件**：可用的 Docker 引擎及執行權限。這台機器目前找不到 docker，不會未經要求安裝系統級軟體、修改虛擬化設定或重啟電腦。

**容器驗收**：build、health、CRUD、記憶與快取持久化、重啟／停止與 volume 恢復；僅有 Dockerfile 不算驗收完成。

**若要公開 API，另需決定**：登入方式、使用者與 scope 的擁有權／角色、部署平台與網域、持久磁碟／備份、允許的 origin、共享 rate limit、持久化用量與硬性費用上限。預算 reset 也須受授權保護，不能公開給任意使用者。

如果目前只發布 GitHub 上的本地 skill，公開網站／多租戶 API 可以不列為該版必備；這是縮小發行範圍，不是把服務的未完成項目假裝驗收成功。

## 最小下一步

先確認「離線 skill 發行」或「完整真實模型研究」的驗收範圍。前者優先補展示、乾淨安裝與 private CI；後者再提供模型／資料／預算條件並凍結品質 rubric。Docker 與公開 API 視最終發行範圍安排。
