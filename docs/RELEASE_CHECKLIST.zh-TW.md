# Private 到 Public：完成與驗收清單

更新：2026-10-06。此清單追蹤「可下載的本地 skill」與「完整研究專案」兩種不同完成條件。先前修正輪未 push；最新一輪使用者授權 commit／push，GitHub metadata 顯示 repo 已是 public，沒有更改 visibility、建立 Release 或部署公開服務。最新提交與安裝驗收見 [PROGRESS](../PROGRESS.md)，研究修正與所需條件見 [FIXES_AND_REQUIREMENTS](FIXES_AND_REQUIREMENTS_20261006.zh-TW.md)。

## A. Skill 下載版

- [x] 支援本地記憶管理與研究接續兩種模式，沒有默默記錄對話。
- [x] 完整 SKILL.md、UI metadata、helper、協定與研究參考。
- [x] README 快速入口、Windows / macOS / Linux 安裝教學、完整操作教學與疑難排解。
- [x] demo JSON、scope 隔離、來源與實際 ID、明確寫入／修改／刪除授權。
- [x] MIT LICENSE；可重現 skill ZIP、檔案 manifest 與 SHA-256，不含 live 資料庫。
- [x] 解壓後從其他目錄執行，完整示範請求與拒絕覆蓋的測試通過。
- [x] TTL 修正保留原到期時間，過期記憶拒絕復活，修正可附新來源參考。
- [x] 本機完整 pytest / unittest、Ruff 與 mypy 驗證；數目以 PROGRESS 為準。
- [x] Python wheel build 及全新無依賴環境的離線核心安裝驗收，三輪記憶操作／scope／TTL 通過。
- [x] CI 定義在 Python 3.11 / 3.12 上測試並產生 ZIP artifact。
- [x] README 一行 `npx skills@1.7.0` 安裝入口、本地 CLI 安裝驗收、八檔完整性及三步操作 smoke；CI 包含相同驗收。
- [x] cache hit 抽取、L3 額外呼叫／成功用量與配額錯扣修正，138 tests／62 subtests 通過，lint／format 已修復。
- [x] UTF-8 demo 文字修復；本機 skill 先備份再同步，最新 wheel 在新隔離環境驗證 L3 與抽取。
- [x] 已 push 並驗證提交 `19ac1ed` 的遠端 Python 3.11／3.12 CI 與兩個 skill artifacts；[run 37480162794](https://github.com/Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents/actions/runs/37480162794) 成功。
- [x] GitHub 公開 URL 乾淨 clone、官方 CLI skill 下載／安裝、八檔完整性及 remember／retrieve／list 通過；未覆蓋本機全域 skill。
- [ ] 使用另一台機器或乾淨環境，從 GitHub 安裝 runtime 與 skill，跑完整教學。
- [ ] 檢查所有待發布檔案與 Git 歷史，確認沒有金鑰、個資、私有筆記、授權不明素材。
- [ ] 對版本打 tag 並建立 GitHub Release，上傳 ZIP 與公布 checksum（需維護者授權）。
- [ ] 使用無 repo 權限的訪客核對下載；只有維護者確定完成後才轉 public。

GitHub 已可下載原始碼並以 npx 安裝 skill，遠端 CI artifact 已產出；尚未建立 Release。官方現行建議將可重用分發包製成 plugin；本版先提供使用者要求的 standalone skill，可由 npx 或 `$skill-installer` 安裝。plugin registry / marketplace 上架不是本輪成果。

本輪 wheel 在另一個新建 venv 中以 `--no-index --no-deps` 安裝，隔離模式確認從該環境的 site-packages 匯入，沒有靠 editable checkout 才通過。這驗證離線核心與 JSON bridge；沒有安裝第三方依賴，不能說已完成 API／OpenAI adapter 的乾淨環境驗收。完整使用者安裝仍需依安裝教學取得依賴。

本機待發行包為 `dist/memlite-agent-skill-0.1.0-20261005.zip`；SHA-256 `aa84da335aaedca25085c1cf62861570fddf1b9a8f0ed0234ae1b51803664630`。更新 skill 或包內說明時，重新產生新檔名並核對新 checksum，不能繼續沿用此數值。

2026-10-06 新修正包：`dist/memlite-agent-skill-0.1.0-fixed-20261006.zip`，SHA-256 `6683b4f713ff3785a1c2a7ff2e5709ce9035c4a4fbf25e6c1a45b90b4aa7ebe2`；新 wheel 位於 `dist/runtime-fixed-20261006/`，已在新環境驗證 L3 與 cache hit 抽取。上段舊包僅為歷史，不上傳舊版假裝是最新功能。

## B. 完整研究專案

| 項目 | 完成條件 | 目前情況／接續方式 |
| --- | --- | --- |
| 重要記憶保護 | 固定容量、配對比較，保留退步與污染 | 首輪完成，22 案例、858 trace；不是預設 |
| 衝突治理 | 有可追蹤來源與明確修正；不將模型信心當真偽 | TTL／新來源修正完成；自動發現矛盾與可信證據評估尚未做 |
| 獨立資料 | 事先凍結真實或獨立撰寫案例與品質判準 | 現在 splits 共用模板，不宣稱 held-out；下一輪另訂固定資料 |
| RQ1 | 比較 token 與真實任務品質，不能只看 retrieval pass | 離線 retrieval 初步完成；待真實回答品質評估 |
| RQ2 | 語意改寫快取正確性、實際 usage 與延遲 | fake exact repeats 完成；待模型／資料與費用授權 |
| RQ3 | eviction 污染與保護的品質比較 | 受控首輪完成；獨立資料與衝突處理仍待驗收 |
| RQ4 | Agent 壓縮整合、不同 budget 的回答品質曲線 | L2/L3 已整合，L3 成功回傳用量與 cache hit 已測；真實回答品質仍待驗收 |
| 自動記憶抽取 | 明確授權、保留來源、污染評估 | opt-in 關鍵字抽取與 cache hit 副作用完成；污染／矛盾評估未做，LLM 句子不等於事實 |
| 展示素材 | 與實測一致的 UI／GIF／完整簡報 | 尚待完成；如果改以 GitHub+CLI 展示，需明確調整規格，不能自動勾選 |
| 容器 | 實際 build / health / 持久化 / 重啟驗收 | 檔案存在；本機沒有 docker，未完成容器驗收 |
| 公開 API | 身分驗證、scope 授權、rate limit、成本上限與持久化 | 目前僅供本地展示，不能直接暴露為多租戶服務 |
| 公開部署 | 使用者授權的平台、預算與可訪問環境 | 未部署；GitHub 發布 skill 與公開 API 是不同事情 |

## C. 推進順序

1. 先完成可離線進行的衝突案例、壓縮整合與固定品質評測，逐輪更新 PROGRESS 與證據。
2. 凍結獨立資料與人工品質判準，避免依 evaluation labels 調參後假裝 held-out。
3. 取得真實 provider 的模型、可用 key、費用上限與資料傳送授權後，量測 usage／品質／延遲；不在文件或 Git 中儲存金鑰。
4. 在 Docker 可用的環境完成容器驗收，再依確定的展示範圍補素材與簡報。
5. private repo 上驗證 CI、另一台機器安裝與發行檔，再由維護者判斷是否 public。

「完成研究」可以包含負面結果；不要求每個策略都優於 baseline。但尚未跑過的實驗與尚未部署的服務，不能以假設完成或程式存在替代驗收。
