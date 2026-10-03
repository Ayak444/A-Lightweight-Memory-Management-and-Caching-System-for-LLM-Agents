# Skill 安裝與實作強化紀錄

日期：2026-09-14。依現有 Python 3.11、SQLite、離線 provider 架構，先強化檢索邊界，未展開 API/UI/部署。

## 已安裝的 skills

安裝位置：`C:/Users/Ayak4-PC/.codex/skills/`。下一回合可自動選用，本次已直接讀取並套用。

| Skill | 來源 | 對應需求與本次使用 |
| --- | --- | --- |
| security-best-practices | openai/skills 的 skills/.curated/security-best-practices | 安全檢視；依 SQLite source-of-truth 原則補上檢索隔離驗證 |
| memlite-repo-planner | 本次建立，專案副本在 docs/skills/ | project-planner、repo-explorer；核對 ADR、程式與落後的 README |
| memlite-implementation | 本次建立，專案副本在 docs/skills/ | implementation、debugger、test-engineer、code-reviewer；先重現，再修正與審查 |
| memlite-benchmark-runner | 本次建立，專案副本在 docs/skills/ | benchmark-runner、experiment-runner、research-documenter；固定資料集前後比較 |

官方 curated 清單沒有使用者表格中的同名 skills，因此沒有把自建 skill 冒稱為官方套件。三個自建 skills 均通過 skill-creator 的 quick_validate.py。安全 skill 的 Python 參考文件針對 Web frameworks；目前核心沒有這些框架，本次只套用一般安全原則與 repo 的資料隔離要求，不宣稱完成全面安全稽核。

## 實作結果

- `memlite/policies/retrieval.py`：從 metadata 再驗證 scope/type，不依賴 vector adapter 的篩選宣告；在建立 trace 和 touch 前排除非法候選。
- 重複 memory ID 只保留第一個有限分數命中；NaN、Infinity 命中被忽略，不會消耗 context 或重複計算存取。
- 驗證 similarity 門檻在 0–1、half-life 有限且正值、權重有限且非負並加總為 1。零權重仍支援 ablation。
- metadata store、vector index、retrieval service 統一 `memory_types=set()` 為空結果；`None` 保留不限型別的語意。這是明確的行為變更，原先空集合會等同不篩選。
- 更新 README，對齊已存在的 embedding、retrieval 與 benchmark 能力。

## 驗證

原有 14 個測試通過。新增邊界測試先在舊實作重現錯誤，再完成修正；目前 18 個測試通過。包含未授權候選不出現在 trace、不增加 access_count，以及零權重設定仍可使用。

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m ruff check memlite tests
.venv/Scripts/python.exe -m mypy memlite
python -m memlite.benchmark_cli --summary-only
```

Ruff 通過；mypy 檢查 23 個來源檔案無問題。完整測試包含 comparison benchmark 的報表輸出驗證。

Benchmark：Python 3.11.9，dataset 1.0.0，10 queries，預設 DeterministicHashEmbedding 與 RetrievalConfig，使用臨時資料庫。

Dataset SHA256：`D0DB450685C312BC21C52E998159D5FBBF4A0587E378518FBEFE16DDB54DEA90`。

| 指標 | 修改前 | 修改後 |
| --- | ---: | ---: |
| Pass rate | 0.70 | 0.70 |
| Mean precision | 0.60 | 0.60 |
| Mean recall | 0.80 | 0.80 |
| MRR | 0.80 | 0.80 |
| Retrieval p50 ms | 0.7891 | 0.8003 |

通過定義為包含全部 expected memories，且沒有 forbidden memories；不是 LLM 回答成功率。兩次單次延遲僅供紀錄，不足以主張效能提升或退步。JSON 摘要保存於 `experiments/results/hardening-20260914/`（依既有 ignore 規則保留本機）。

## 後續優先工作

1. 索引可恢復性：embedding/upsert 失敗時保留 metadata，記錄 missing-index 狀態；以故障注入驗證重建後恢復。現有跨 DB 寫入仍非原子操作。
2. 候選補足：大量過期或失效索引可能佔滿 candidate_limit，導致有效記憶沒進入候選；新增固定時鐘案例，設計有上限的補取策略。
3. Cache 垂直切片：先 exact cache，再 semantic cache；驗證 scope、model、system prompt、tool schema、context fingerprint、TTL 與 invalidation。
4. 真實 embedding 的受控比較：保持資料集與設定一致，追蹤目前未通過的 3 組查詢，不以調低驗收標準換取通過率。
