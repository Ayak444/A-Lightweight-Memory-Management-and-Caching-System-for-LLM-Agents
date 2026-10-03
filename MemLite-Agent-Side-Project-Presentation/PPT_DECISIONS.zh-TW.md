# MemLite-Agent 簡報決策紀錄

## 已確認內容

- 簡報語言：繁體中文，保留必要英文技術名詞。
- 作者姓名：陳格洋。
- 使用情境：放在 GitHub 上供讀者自行閱讀，不以固定口頭簡報時間設計。
- 專案敘事：簡報先以 MVP 已完成的角度呈現。
- 個人背景：大學生，透過實作理解 LLM Agent 長期任務中的 context、成本、重複查詢與錯誤記憶問題。
- GitHub、聯絡方式、團隊貢獻與 Logo：不需要獨立頁面或額外欄位。

## 建議的大學生動機說詞

在學習與實作 LLM Agent 的過程中，我發現模型雖然能保留對話內容，但對話越長，送入模型的 context、等待時間與 API 成本也會持續增加。現有框架可以很快做出功能，卻不容易看清楚某一段記憶為什麼被保存、取回，或如何影響最後答案。

因此我希望從底層實作一個輕量化系統，把 Working、Episodic、Semantic Memory 與 Semantic Cache 拆開管理，並用可重現的 benchmark 比較不同策略。這個 side project 不只是串接 LLM API，也是一次對資料建模、搜尋、快取、測試與系統評估的完整練習。

## 後續再補

1. 真實 benchmark 圖表與數據。
2. 實際產品介面或 demo 截圖。

未取得真實結果前，不在簡報中虛構 token、latency、cost 或 task success 的改善比例。

