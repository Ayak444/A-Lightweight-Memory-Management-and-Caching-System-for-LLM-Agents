# Agent 壓縮整合與可追蹤修正

日期：2026-10-05。接續重要性保護的負面結果，完成兩個本地可驗證切片：保留 TTL 的明確修正，以及 Agent L2 壓縮與必要事實保留實驗。未呼叫真實 API。

## 一、TTL 與來源修正

原本 MemoryManager 替換記憶時沒有帶入 expires_at，會將 TTL 記憶變成永久記憶；skill 以拒絕修正防止遺失。現在新版本保留**原始絕對到期時間**，不重新計算 ttl_seconds；過期記憶與恰好在截止時間的記憶不能復活。

例如 120 秒 TTL 的記憶，在第 90 秒修正後，只剩原本的 30 秒。permanent 記憶仍為 permanent；只有另行授權的新建記憶才能取得新的存活期限。

skill 的 supersede 可附 `source` 與 `source_ref`，記錄新事實的來源，不自行沿用可能失效的舊來源。這只是可查看的參考，不驗證來源權限、真實性或矛盾。confidence / importance 仍可能不可靠，沒有自動啟用保護或刪除其他記憶。

新增 6 個測試，覆蓋固定時鐘下的 TTL 不延長、到期拒絕、版本關係、向量清理、scope 快取失效、來源重新開啟後仍存在、錯誤參數與跨 scope 不修改原文。原有 bridge 測試改驗證 TTL 可安全修正。metadata transaction 保留版本與關係，但四個 SQLite 檔案仍無跨檔原子性。

## 二、Agent L2 壓縮

以 `PromptBuilder(memory_token_budget=...)` 明確選用 extractive compression，預設 `None` 保持既有內容。只壓縮選入的記憶 payload，不改資料庫、system instruction、使用者問題或對話歷史；budget 不是整個 prompt 的上限。

Agent 的既有快取指紋以實際 prompt context 計算，因此不同壓縮結果不會誤用舊快取。不新增 provider 呼叫；抽取式壓縮沒有付費摘要。L3 仍只有獨立函式，尚未接入 Agent。

新增 6 個整合測試，驗證實際 provider 收到的文字、預設相容、預算變動快取隔離、空 context、不選入被拒絕或跨 scope 記憶、參數驗證。runner 另有 2 個測試。

## 三、固定離線實驗

| 項目 | 設定 |
| --- | --- |
| Dataset | `experiments/datasets/compression.json`，`compression-1.0.0` |
| SHA-256 | `997657ff846dd580416ec9f0387be5caddccc204af31dc68f7b6f3007735e855` |
| 案例 | 6 個人工撰寫壓力案例：短事實、多事實、否定、數值單位、中文 query、必要長句 |
| Baseline | 全部 selected context，與預算 8 / 16 / 32 / 64 / 128 |
| Retrieval | 每題一個來源；max_results 1、min_similarity 0、L1 budget 5000，隔離 L2 效果 |
| 重複 | 每題每策略重建資料庫 3 次，共 108 筆實際 Agent prompt trace |
| Provider | recorder，僅儲存送入的 prompt，回覆不計入品質評分 |
| 穩定性 | 三次 context 一致，0 預算違規、0 原始內容改寫 |
| 環境 | Python 3.12.14、Windows 11；dirty git `787418f47526d06b305ad27a89385166602cf5a7` |
| 執行記錄 | 2026-10-05T14:53:06 UTC，source hashes 保存於 report |

必要事實是從原文預先指定的字串，標籤不送給 retrieval、compressor 或 provider。只計算實際記憶 context，不能因 query 本身提到答案而誤算保留。

| 策略 | 所有必要事實都保留的題目 | Macro 事實保留率 | 平均 payload token 估計 | Macro payload 剩餘比例 | 平均整體 prompt token 估計 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 不壓縮 | 6/6 | 100% | 39.00 | 1.0000 | 84.17 |
| L2 budget 8 | 1/6 | 30.56% | 7.17 | 0.3366 | 52.33 |
| L2 budget 16 | 1/6 | 52.78% | 11.33 | 0.4689 | 56.50 |
| L2 budget 32 | 5/6 | 83.33% | 21.33 | 0.7813 | 66.50 |
| L2 budget 64 | 5/6 | 83.33% | 23.67 | 0.8451 | 68.83 |
| L2 budget 128 | 6/6 | 100% | 39.00 | 1.0000 | 84.17 |

token 為 ceil(UTF-8 bytes/4)，不是 tokenizer 或 API usage；整體 prompt 估計包含各訊息文字，但不含模型 framing overhead。Macro ratio 是每題比例的平均，不等於平均 token 相除。

## 四、失敗與解讀

budget 32 / 64 仍丟失 `long_required_sentence` 的「取得操作員核准後才能恢復 vault key」條件，因完整必要句超出預算，compressor 不會切句或憑空縮寫。budget 8 / 16 丟失更多事實；中文 query 沒有 whitespace token overlap 時，只能依原始句序選擇，不能說已具中文語意理解。

budget 128 在這 6 題保留全部事實，但沒有節省；不能宣稱找到不降品質的通用 sweet spot。字串保留也不能驗證句子真偽、推理正確或完整語意。

**RQ4 從「沒有實驗」進展為「Agent L2 已整合、事實保留代理指標已量測」；真實回答品質的轉折點仍未完成。** deterministic repeats 不是 18 個不同任務，不做顯著性或 production 成本主張。

## 五、重現與接續

```bash
python -m memlite.evaluation.compression_benchmark --dataset experiments/datasets/compression.json --output experiments/results/my-compression --repeats 3
python -m pytest -q tests/test_agent_compression.py tests/test_compression_benchmark.py tests/test_ttl_correction.py
```

正式原始資料位於 `experiments/results/compression-20261005-verified/`，含 report、逐題實際 prompt trace、CSV、dataset snapshot 與 environment。依既有 ignore 規則保留本機；固定輸入、runner、測試與本報告可版控，不放入 skill 包。

下一步先凍結獨立任務、人工品質 rubric、baseline 與 model / token 記錄方式，再取得費用與資料傳送授權後評估真實回答。公開前剩餘工作見 [驗收清單](RELEASE_CHECKLIST.zh-TW.md)，總進度見 [PROGRESS](../PROGRESS.md)。
