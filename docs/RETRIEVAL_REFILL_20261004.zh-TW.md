# 過期候選漏失修正與驗證

日期：2026-10-04。依 `PROGRESS.md` 接續下一個研究切片，完成檢索候選補足、回歸測試與固定資料的配對實驗。沒有呼叫真實 API、改動 live 記憶資料庫或公開發布。

## 重現與修正

修正前，以真正的 SQLite metadata/vector adapter 執行 `evaluation-expired_candidates`，查詢選取結果為 `[]`，新增回歸測試失敗。原因不是有效記憶不存在，而是 25 筆過期資料先佔滿向量 top-20，metadata 過期檢查移除它們之後，沒有補找後續資料。

修正位於 `memlite/policies/retrieval.py`：

1. `candidate_limit` 計算通過 metadata 檢查的唯一有效候選，而非原始向量 hit。
2. 候選不足時將索引搜尋前綴按倍數擴大，例如 20 → 40；達到有效候選數、索引耗盡或掃描上限就停止。
3. 仍核對 scope、類別、active 狀態與 expiry，排除不存在、重複與非有限分數的 hit。
4. 沿用原本分數、similarity threshold、max_results 與 token budget；因門檻／預算被拒絕不會觸發額外補找。
5. 只 touch 最終選取的記憶一次，不刪除過期資料或偷偷執行淘汰。

向量 API 的參數保持相容；補找依賴「相同索引擴大 limit 時保留已返回的排序前綴」契約，SQLite exact search 符合。未來 ANN adapter 必須支援這個條件或重新設計分頁。

## 可觀測性與上限

| 項目 | 定義 |
| --- | --- |
| `candidate_scan_limit` | 可指定的正整數上限，必須 >= candidate_limit；未指定為 max(100000, candidate_limit) |
| `search_rounds` | 本次索引搜尋呼叫次數；空 types filter 為 0 |
| `scanned_hits` | 最後一輪返回的前綴長度，不是各輪加總或 SQLite 實際掃過的 row 數 |
| `search_limit` | 最後一輪請求的前綴上限 |
| `scan_limit_reached` | 有效候選仍不足且已到上限，結果可能被截斷；不代表一定存在漏掉的正解 |

這些欄位會由 retrieval 的 JSON 輸出及 challenge 的逐題 trace 記錄。若設定 `candidate_scan_limit=20`，可模擬原本 top-20 不補候選的邊界，作為控制組。它不是新的最佳化門檻。

## 配對實驗

固定 `challenge-1.1.0`，SHA-256：`54d1809facacd36c64018ba38b25a2c720fe297daf26fed6fafd5a4eadc1d239`。12 個案例、17 個策略、兩種條件各重複 3 次，共 1,224 筆 trace。資料、ID、初始時間、存取歷史、權重、門檻、token budget 與容量相同，只切換候選掃描上限。

控制組的 selected/evicted 清單與 2026-10-03 已保存的原始結果逐題一致。兩組內的三次重複也一致；重複執行不代表增加獨立樣本數。

Evaluation 各策略仍只有 6 個獨立 synthetic 案例：

| 策略 | 原本 Pass | 修正後 Pass | 原本 Recall | 修正後 Recall |
| --- | ---: | ---: | ---: | ---: |
| 全歷史 B0 | 50.00% | 50.00% | 1.0000 | 1.0000 |
| 最近十筆 B1 | 0.00% | 0.00% | 0.5556 | 0.5556 |
| Hybrid top-1 | 50.00% | 66.67% | 0.5556 | 0.7222 |
| Hybrid top-3 | 50.00% | 66.67% | 0.6667 | 0.8333 |
| TTL + top-3 | 66.67% | 66.67% | 0.8333 | 0.8333 |
| LRU cap 2/4/8，各容量 | 0.00% | 16.67% | 0.2222 | 0.3889 |
| LFU cap 2/4，各容量 | 16.67% | 33.33% | 0.2778 | 0.4444 |
| LFU cap 8 | 16.67% | 33.33% | 0.4444 | 0.6111 |

TTL + LRU/LFU 各容量的 selected/evicted 皆不變。所有 capacity 策略使用 top-3。

兩個 split 的 expired_candidates 案例，8 個未事先清理 TTL 的檢索策略，各重跑 3 次，合計 **48 筆 trace 改善**；這不是 48 個獨立案例。變化只發生在這兩個過期候選案例，沒有其他選取差異、淘汰清單差異或原本通過題目變失敗。

修正後該案例選入 `correct`，前綴由 20 擴大到 40、第二輪實際返回 26 筆，搜尋呼叫由 1 次變 2 次。25 筆過期記憶仍存在；讀取沒有刪除它們。原本「先做 TTL 清理，檢索才能成功」的差異因此消失，說明前輪 TTL 的一題優勢含有 candidate starvation 的實作因素，不能當成 TTL 能判斷真假或提升普遍品質的證據。

## 一般回歸與測試

原本 `mvp.json` v2.0.0 的 31 題重新執行。7 個檢索策略與 6 個 token-budget 設定的 pass、precision、recall、MRR、平均估計 token，與前輪 JSON 完全一致。Hybrid top-1 仍通過 29/31 題，Hybrid top-3 仍通過 25/31 題。

新增 6 個 refill 測試及 2 個配對實驗測試，涵蓋真實 SQLite 重現、跨 scope/type/status 過濾、expiry 邊界、非有限分數、去重、只 touch 一次、上限截斷、索引耗盡、超量 backend hit、防覆寫與歷史控制驗證。

已驗證：完整 pytest **87 tests、29 subtests 通過**，unittest discovery 的 87 tests 亦通過；Ruff lint/format 通過；mypy 檢查核心加配對 runner 共 43 個來源檔通過。測試僅使用暫存資料庫。

## 重現與檔案

```powershell
rtk proxy .venv-research/Scripts/python.exe -m experiments.run_refill_comparison --dataset experiments/datasets/challenge.json --output experiments/results/new-refill-run --repeats 3
```

若本機有前輪輸出，可另加 `--reference experiments/results/research-challenge-20261003-v2` 核對歷史 selected/evicted；未提供時會記錄 `baseline_matches_reference: null`，不能宣稱已核對原始紀錄。

正式配對輸出為 `experiments/results/refill-20261004-verified/`，含兩組完整 report、query traces、dataset snapshot、environment，以及 `refill_comparison.json/csv`。前輪結果與先跑的 `refill-20261004/` 均保留，不覆寫。31 題回歸位於 `experiments/results/retrieval-regression-20261004/`。原始輸出依既有規則保留本機；此文件、資料集及 runner 可版控與重現。

研究參數與核心原始碼 checksum 記錄在 report；配對 runner 另記錄自身 checksum。架構決策見 [ADR 0007](adr/0007-metadata-aware-candidate-refill.md)。

## 限制與下一個切片

- 所有數據是 synthetic retrieval 品質，不是 LLM task success；共用模板的 split 不是獨立真實 held-out validation。
- SQLite 每一輪 search 仍會掃描並排序整個符合 scope/model 的向量 corpus。前綴上限不等於底層 row scan、費用或延遲上限；大量 stale index 可能造成額外開銷，超過 cap 仍可能漏失。
- 初跑配對實驗與其他驗證工作重疊，因此另行單獨重跑正式配對；即使單獨重跑，本機小樣本計時也只作描述，不宣稱 production 加速或固定延遲。
- 此修正沒有解決 active 但錯誤的熱門記憶、衝突 context 或 LRU/LFU 刪掉冷門重要記憶的問題，也沒有提供跨資料庫原子快照。
- 下一個切片：訂出「重要記憶保護」的明確規則，在固定容量下與 LRU/LFU 比較，同時檢查熱門污染是否被意外保護。不要根據本輪 evaluation 正解設定 oracle 權重；保留獨立資料驗證、真實 provider 與壓縮品質研究待做。
