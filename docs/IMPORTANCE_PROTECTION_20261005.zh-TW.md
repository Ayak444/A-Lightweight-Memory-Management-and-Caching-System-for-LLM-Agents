# 有上限的重要記憶保護：改善與污染風險

日期：2026-10-05（Asia/Taipei）。本輪接續 PROGRESS 指定的固定容量重要性保護研究，未使用遠端 API、未付費、未公開 repo。

## 問題與規則

LRU/LFU 會丟掉很久沒用但重要的記憶；保留重要記憶能否改善？若 importance / confidence 被錯誤標高，會不會把污染也保留下來？

新增可選用的 `ImportanceProtectedEviction`，包住既有 LRU/LFU；固定規則為 importance >= 0.8、confidence >= 0.8，最多保留 1 筆，名額在總容量內。超額合格記憶依 importance 降序、confidence 降序、ID 升序決定；其他記憶依原始 LRU/LFU 排序淘汰。不覆蓋 TTL、scope 或型別，不改預設策略。

重要性與信心是呼叫者提供的評分，**不是來源驗證，也不是真實性判定**。實驗 expected/forbidden 標籤只用於評分，不送給 policy；新壓力案例故意將錯誤記憶標高，測試不可靠 metadata。

## 固定條件與證據

| 項目 | 設定／實測 |
| --- | --- |
| Dataset | `experiments/datasets/protection.json`，`protection-1.0.0` |
| SHA-256 | `92e14bf3c4f75bc36d5bcfcd5211bdd7e29280f6e4c0b06141b69366048fadeb` |
| 案例 | 原 challenge 12 題完全不變，另加 10 題；共 22 題 |
| Splits | development / evaluation 各 11 題，共用模板與不同詞彙，不是真正 held-out |
| 策略 | 無淘汰 top-3；LRU/LFU × capacity 2/4/8 × 開／關保護，共 13 策略 |
| Retrieval | deterministic lexical hash，固定 top-3、candidate_limit 20、budget 500 |
| 重複 | 每個案例／策略重建獨立資料庫 3 次，858 筆 trace、396 筆保護／控制配對 |
| 選取／淘汰／保留穩定性 | 三次一致 |
| 歷史控制一致性 | 原 12 題 × 7 控制策略 × 3 次，252 筆選取與淘汰結果一致 |
| 環境 | Python 3.12.14，Windows 11，git `787418f47526d06b305ad27a89385166602cf5a7`，dirty checkout |
| 時間 | environment.json：2026-10-05T14:53:55 UTC；各核心原始碼 hash 另存於 report |

每次比較從相同固定 ID、時鐘、頻率與存取時間開始，不以真實存取累積製造差異。沒有依 evaluation 結果調整門檻、權重或保護名額。

## Evaluation 結果

以下為 11 個不同案例的 macro 結果；每題三次結果相同。必需記憶保留率量測淘汰後還在資料庫的 expected 比例；recall 量測最後實際選入的 expected 比例，兩者不同。

| 容量策略 | 通過率（關 → 開） | Recall（關 → 開） | 必需記憶保留率（關 → 開） | 命中 forbidden 的題目比例（關 → 開） |
| --- | ---: | ---: | ---: | ---: |
| LRU cap 2 | 36.36% → 36.36% | 0.4848 → 0.6061 | 0.4848 → 0.6061 | 18.18% → 27.27% |
| LFU cap 2 | 45.45% → 45.45% | 0.5152 → 0.6364 | 0.5152 → 0.6364 | 18.18% → 27.27% |
| LRU cap 4 | 36.36% → 36.36% | 0.4848 → 0.6061 | 0.4848 → 0.6061 | 18.18% → 27.27% |
| LFU cap 4 | 45.45% → 45.45% | 0.5152 → 0.6364 | 0.5152 → 0.6364 | 18.18% → 27.27% |
| LRU cap 8 | 18.18% → 27.27% | 0.5455 → 0.6364 | 0.6364 → 0.7273 | 36.36% → 36.36% |
| LFU cap 8 | 27.27% → 36.36% | 0.6667 → 0.7576 | 0.7576 → 0.8485 | 36.36% → 36.36% |

無淘汰 top-3 的通過率為 63.64%、recall 0.9091、保留率 1.0，仍有 36.36% 的題目選入污染。不能把不同容量的通過率當成單調品質曲線：增加容量也會留下更多錯誤候選。

## 逐題變化

- `cold_important`：兩個 split、六個容量策略、三次重複，36 筆由失敗變通過。每個 split 是同一模板，不能說有 36 個獨立任務成功。
- `important_poison`：cap 2/4 的 LRU/LFU 共 24 筆由通過變失敗。錯誤事實被保留並選入，正確事實仍在，但 pass 要求無污染。
- `important_poison`：所有容量共有 36 筆保留 forbidden 記憶。cap 8 原本就沒有必要刪除這題的 7 筆記憶，控制也失敗，因此不能將這 12 筆算成新增退步。
- `protected_overflow`：cap 2 可多保留三筆必要事實中的一筆，但仍不足以通過；保留率上升不等於任務成功。
- `low_confidence_poison`：錯誤記憶 confidence 0.2，不取得保留名額。這不代表低信心門檻能驗證其他記憶的真實性。
- `ordinary_rare`：importance 0.5 的冷門正確事實仍可能被刪除；不能宣稱此機制保護所有冷門記憶。
- `expired_important`：高重要性不能恢復過期記憶；沒有容量違規，沒有改動其他 scope。

## 重現

在 repo 根目錄，使用已安裝開發依賴的 Python。output 必須是新的／空的資料夾：

```bash
python -m memlite.evaluation.protection_benchmark --dataset experiments/datasets/protection.json --output experiments/results/my-protection --repeats 3
```

有上一輪本機原始資料時，可加 `--reference experiments/results/refill-20261004-verified/refill` 驗證歷史控制。沒有 reference 時欄位為 null，不能宣稱已核對歷史；主要保護／控制配對仍可自行重現。固定 fixture 已隨 repo 提供，不需 `--create-dataset`。

本輪正式原始資料位於 `experiments/results/importance-protection-20261005-verified/`，包括 `challenge_report.json`、`query_traces.json`、`protection_comparison.json`、`protection_pairs.csv`、`challenge_comparison.csv`、`dataset_snapshot.json`、`environment.json`。依既有規則保留本機、不加入 skill 下載包；程式、固定輸入與本報告可版控。TTL 與 L2 整合完成後重新執行本比較，結論不變；核心版本以保存的 source_sha256 為準。

## 驗收與結論

保護 policy 新增 9 個測試，runner 新增 4 個測試；全專案測試與程式品質檢查結果見 [PROGRESS.md](../PROGRESS.md)。架構決策見 [ADR 0008](adr/0008-bounded-importance-protection.md)。

結論是**有限名額能保住被標為重要的冷門事實，但同時會放大錯誤評分造成的污染**。因此不設為預設，不聲稱解決衝突治理。下個研究重點為來源與證據、明確版本修正與獨立資料，而不是只調高重要性權重。

未量測 LLM 回答品質、真實語意理解、付費 token／成本或 production speedup。延遲為本機描述性資料，未做執行次序隨機化或統計顯著性分析。
