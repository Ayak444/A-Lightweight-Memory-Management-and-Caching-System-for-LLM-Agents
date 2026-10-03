# MemLite-Agent Benchmark Results

> Run date: 2026-09-13  
> Dataset: `experiments/datasets/mvp.json` v1.0.0  
> Scope: 10 sequences / 10 retrieval queries  
> Embedding: deterministic lexical hash baseline, 256 dimensions  
> Vector search: persistent SQLite exact cosine scan  
> Remote embedding / LLM latency: excluded

## 執行環境

| 項目 | 數值 |
| --- | --- |
| CPU | AMD Ryzen 7 7800X3D, 8 cores / 16 logical processors |
| Memory | 31.1 GB |
| OS | Windows 11 Pro 10.0.26100 |
| Python | 3.11.9 |
| Test runner | pytest 9.1.1 |

## 1. Retrieval 策略比較

| 策略 | Pass Rate | Precision | Recall | MRR | 平均選入 Token | p50 ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Similarity only, top-5 | 70% | 0.60 | 0.80 | 0.80 | 12.7 | 0.833 | 1.455 |
| Hybrid, top-5 | 70% | 0.60 | 0.80 | 0.80 | 12.7 | 0.775 | 1.402 |
| Hybrid, top-3 | 70% | 0.60 | 0.80 | 0.80 | 12.7 | 0.838 | 1.448 |
| **Hybrid, top-1** | **80%** | **0.80** | **0.80** | **0.80** | **9.2** | **0.754** | **0.845** |
| Hybrid, top-3, threshold 0.20 | 50% | 0.45 | 0.50 | 0.50 | 5.9 | 0.572 | 1.167 |

### 可支持的結論

- 在目前每題只有一個主要 relevant memory 的資料設計下，`hybrid_top1` 表現最佳。
- 相較 `hybrid_top5`，top-1 通過率增加 10 個百分點，Precision 增加 0.20。
- 平均選入 token 從 12.7 降至 9.2，下降約 27.6%。
- p95 從 1.402 ms 降至 0.845 ms，下降約 39.7%；此差異包含較少 touch/update 操作，且樣本小，不能推論為 production 加速比例。
- 0.20 的 strict threshold 過度拒絕詞彙不同但語意相關的記憶，Recall 從 0.80 降至 0.50。

## 2. Token Budget 比較

| Token Budget | Pass Rate | Precision | Recall | MRR | 實際平均 Token |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 40% | 0.40 | 0.40 | 0.40 | 4.4 |
| **16** | **70%** | **0.70** | **0.80** | **0.80** | **10.8** |
| 32 | 70% | 0.60 | 0.80 | 0.80 | 12.7 |
| 64 | 70% | 0.60 | 0.80 | 0.80 | 12.7 |
| 128 | 70% | 0.60 | 0.80 | 0.80 | 12.7 |
| 500 | 70% | 0.60 | 0.80 | 0.80 | 12.7 |

### 可支持的結論

- Budget 8 太小，Pass Rate 與 Recall 都只有 40%。
- Budget 16 已達到 budget 32 到 500 的 70% Pass Rate 與 0.80 Recall。
- 相較 budget 32，budget 16 平均少用約 15.0% token，Precision 反而由 0.60 增至 0.70，原因是少選入無關候選。
- 在目前短記憶資料集上，budget 超過 32 不再帶來品質收益。
- 這只是目前資料分布的 sweet spot，不能直接固定為所有任務的 production 預設值。

## 3. Corpus Size 與 Retrieval Latency

每個 corpus size 預熱一次後量測 30 次。這裡使用 exact cosine scan，未包含遠端 embedding 與 LLM 呼叫。

| Memories | Runs | p50 ms | p95 ms |
| ---: | ---: | ---: | ---: |
| 10 | 30 | 1.094 | 1.227 |
| 100 | 30 | 4.478 | 4.702 |
| 500 | 30 | 22.879 | 28.658 |
| 1,000 | 30 | 46.763 | 55.383 |
| 2,000 | 30 | 90.266 | 99.992 |

### 可支持的結論

- Exact scan 延遲隨資料量近似線性增加。
- 目前原型在 2,000 筆記憶時仍維持 p95 約 100 ms，符合 MVP 本地 retrieval 目標的邊界。
- 若 corpus 繼續成長，必須換成 Chroma/Qdrant 等 ANN backend，而不是繼續最佳化 Python exact scan。
- 這組數字只代表指定硬體上的本地 index，不包含網路與模型延遲。

## 4. 失敗案例

10 題中有 3 題失敗：

| Category | 問題 | 原因 | 下一個實驗 |
| --- | --- | --- | --- |
| Long horizon | 查詢未找到 SQLite source-of-truth 決策 | 查詢和記憶缺少共同詞彙 | 換成真實 embedding 比較 Recall |
| Conflict | 找到正確 SQLite，也選入污染的 MongoDB 記憶 | 扣分不足以阻止候選進入 context | 加入 pollution rejection gate |
| Long horizon | 未找到 MVP 非目標 | lexical similarity 低於 threshold | 比較 real embedding 與 reranker |

## 5. 工程品質摘要

| 指標 | 結果 |
| --- | --- |
| pytest | 14 passed |
| Ruff lint | passed |
| Ruff formatting | passed |
| Strict mypy | passed |
| Dataset validation | 10/10 sequences valid |

## 6. 限制

- 只有 10 個 query，信賴區間不足，不適合做統計顯著性主張。
- Deterministic lexical embedding 是測試 baseline，不代表真正語意模型。
- Retrieval dataset 目前多為單一 relevant memory，因此 top-1 天然較有利。
- Latency 只測本機 exact scan，未包含 API、網路、LLM 或 summarization。
- 尚未實作 Semantic Cache，因此目前沒有 Cache Hit Rate 與 Cost Saving 實測值。
- 後續應將資料集擴充到至少 50 sequences，並重複多次完整 run。

## 原始資料

- `experiments/results/current/comparison.json`
- `experiments/results/current/strategy_comparison.csv`
- `experiments/results/current/token_budget_comparison.csv`
- `experiments/results/current/corpus_latency_comparison.csv`

