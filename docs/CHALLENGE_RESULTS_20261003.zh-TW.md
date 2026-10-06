# 長歷史與 Eviction 受控實驗

> 後續修正（2026-10-04）：本文件保留修正前的歷史結果。candidate starvation 已透過有上限的候選補足處理，新的配對驗證見 [檢索修正紀錄](RETRIEVAL_REFILL_20261004.zh-TW.md)。修正後，TTL 與不先清理 TTL 的 top-3 都為 66.67%，因此不能將本文件的差異全部歸因於淘汰政策品質。

執行日期：2026-10-03。資料版本：`challenge-1.1.0`。本報告取自實際執行，不是示意數字；沒有呼叫遠端 API。

## 問題與固定條件

先前 31 題的 Hybrid top-1 通過率為 93.55%，但題目大多只需要一筆相關記憶，且各 scope 的寫入歷史不超過十筆。因此本輪另建壓力案例，檢查短歷史與單筆答案是否讓原結論過度樂觀，並開始量測 RQ3 的 eviction 影響。

| 項目 | 設定 |
| --- | --- |
| 案例 | 12 個，development / evaluation 各 6 個 |
| 類別 | long_history、three_required、hot_pollution、fresh_correction、cold_important、expired_candidates |
| 策略 | 17 個：B0、B1、top-1、top-3、TTL，以及 LRU/LFU/hybrid × capacity 2/4/8 |
| 重複 | 每個策略／案例 3 次，共 612 筆 query trace |
| 初始狀態 | 每次從獨立臨時資料庫開始，固定 ID、時間、重要性、存取次數與最後存取時間 |
| 固定時間 | 2026-10-03 00:00:00 UTC |
| 檢索 | deterministic lexical hash embedding，256 維；候選 20，budget 500，threshold 0.05 |
| 分數 | similarity 0.55、recency 0.15、importance 0.15、confidence 0.10、frequency 0.05 |
| 標籤隔離 | expected/forbidden 不寫入 ranking metadata，沒有以正解設定 pollution penalty |
| 資料 SHA-256 | `54d1809facacd36c64018ba38b25a2c720fe297daf26fed6fafd5a4eadc1d239` |
| 重複一致性 | 每個策略／案例的 selected 與 evicted 清單三次均一致 |

development 使用 atlas，evaluation 使用 beacon；不同 scope 與詞彙，但共用案例模板。這不是來自獨立分布的真正 held-out validation，也不代表實際使用比例。沒有根據 evaluation 結果調整模型、檢索權重、threshold 或容量。

初跑 `challenge-1.0.0` 將相同 age 的後寫入項目設定為較舊的秒數；逐題核對後更正為依插入順序遞增，並升版為 1.1.0、另開 output 目錄重跑。初跑保留在 `research-challenge-20261003`；正式結論僅採 `research-challenge-20261003-v2`。這是初始條件修正，不是調整策略讓特定結果勝出。

## Evaluation 組結果

每個策略的獨立案例只有 6 題，重跑三次不會使獨立樣本數變成 18。Precision / Recall / 污染比例均為逐 query macro 平均。Pass 要求所有 expected 被選入，而且沒有 forbidden；**不是 LLM 任務成功率**。空選取的 precision 與污染比例設為 0，必須同時查看 recall。

| 策略 | Pass | Precision | Recall | 污染比例 | Forbidden Hit | 平均估計 Token |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 全歷史 | 50.00% | 0.1264 | 1.0000 | 42.69% | 50.00% | 143.83 |
| B1 最近 10 筆 | 0.00% | 0.1000 | 0.5556 | 41.67% | 50.00% | 88.67 |
| Hybrid top-1 | 50.00% | 0.6667 | 0.5556 | 16.67% | 16.67% | 8.67 |
| Hybrid top-3 | 50.00% | 0.3333 | 0.6667 | 27.78% | 33.33% | 27.17 |
| TTL + top-3 | 66.67% | 0.5000 | 0.8333 | 27.78% | 33.33% | 29.17 |
| LRU cap 2 | 0.00% | 0.1667 | 0.2222 | 25.00% | 33.33% | 18.00 |
| LFU cap 2 | 16.67% | 0.2500 | 0.2778 | 33.33% | 33.33% | 18.33 |
| TTL + LRU cap 2 | 16.67% | 0.3333 | 0.3889 | 25.00% | 33.33% | 20.00 |
| TTL + LFU cap 2 | 33.33% | 0.4167 | 0.4444 | 33.33% | 33.33% | 20.33 |
| LRU cap 4 | 0.00% | 0.1111 | 0.2222 | 27.78% | 33.33% | 27.33 |
| LFU cap 4 | 16.67% | 0.1667 | 0.2778 | 33.33% | 33.33% | 27.67 |
| TTL + LRU cap 4 | 16.67% | 0.2778 | 0.3889 | 27.78% | 33.33% | 29.33 |
| TTL + LFU cap 4 | 33.33% | 0.3333 | 0.4444 | 33.33% | 33.33% | 29.67 |
| LRU cap 8 | 0.00% | 0.1111 | 0.2222 | 27.78% | 33.33% | 27.33 |
| LFU cap 8 | 16.67% | 0.2222 | 0.4444 | 27.78% | 33.33% | 27.17 |
| TTL + LRU cap 8 | 16.67% | 0.2778 | 0.3889 | 27.78% | 33.33% | 29.33 |
| TTL + LFU cap 8 | 33.33% | 0.3889 | 0.6111 | 27.78% | 33.33% | 29.17 |

所有 capacity 策略皆使用 top-3。Token 是 UTF-8 bytes/4 向上取整估計，只含選取的記憶，不是 LLM 完整 prompt 用量或帳單。

## 逐題發現

1. **長歷史**：B0 能保留舊 region，B1 最近十筆漏掉它；top-1/top-3 能找到相關事實。LRU cap 2/4/8 仍會刪除這筆很久未存取的資料。
2. **三筆必要事實**：top-1 只選 runtime，recall 為 1/3；top-3 選入 runtime、region、database，通過。不能把 top-1 宣稱為所有 Agent 工作的最佳預設。
3. **熱門污染**：近期、常用的 obsolete database 記憶壓過正確資訊；LRU/LFU cap 2 會淘汰 correct，仍留下 wrong。常用不等於正確。
4. **新修正**：top-1 只選 correct，通過；top-3 同時選 correct 和 wrong，仍失敗。Recall 1.0 不代表 context 沒有錯誤。
5. **冷門但重要**：top-1 找到 recovery；LRU/LFU cap 2 淘汰 recovery。容量政策尚未提供重要事實保護。
6. **過期候選塞滿**：25 筆 expired 的相似度高於正確記憶，先佔滿向量 top-20，再被 metadata expiry 檢查移除；普通檢索回傳空結果。TTL 清除全部 25 筆 expired vectors 後能選入 correct。

TTL 的一題改善來自清掉過期索引、避免 candidate starvation，不能推論它能辨識未過期的錯誤事實。LFU 同頻率時沿用 metadata 查詢的穩定順序；本資料有同頻率項目，不能把 tie-breaking 帶來的優勢解讀為一般性的記憶品質提升。

## 重現與證據

```powershell
rtk proxy .venv-research/Scripts/python.exe -m memlite.evaluation.challenge_benchmark --dataset experiments/datasets/challenge.json --output experiments/results/new-challenge-run --repeats 3
```

固定資料已加入 repo，不需再次產生。指定新 output 目錄，保留先前證據。正式原始輸出：`experiments/results/research-challenge-20261003-v2/`，依既有 ignore 規則保留本機。包含：

- `challenge_report.json`：完整參數、17 策略 × 2 組 aggregate、資料 checksum、所有核心 Python 原始碼 checksum。
- `challenge_comparison.csv`：可供圖表與簡報讀取的比較資料。
- `query_traces.json`：612 筆逐題 selected、evicted、品質與時間。
- `dataset_snapshot.json`：本次輸入快照。
- `environment.json`：Python、平台、Git commit、dirty 狀態與套件版本。

本報告可版控；原始 JSON/CSV 可透過固定資料與 runner 重現。執行時間排除資料庫建立，eviction/retrieval 分開量測；小量本機計時、執行順序與磁碟狀態不能作為 production latency 證據。

驗證：79 tests、18 subtests 通過，Ruff lint/format 與 mypy 42 個來源檔通過。skill JSON 介面、scope、TTL、UTF-8 與跨工作目錄 helper 亦通過測試；skill 格式驗證通過。

## 下一步

RQ3 從「未實驗」更新為「完成首輪 synthetic 受控比較」，不是完成全部研究。優先修正 expired candidate starvation 並重跑同一資料，再研究重要性保護與衝突記憶治理。真正獨立的 held-out 任務、語意 embedding、LLM task success、compression 品質與 API 延遲／成本仍未驗證。
