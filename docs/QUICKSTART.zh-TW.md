# MemLite-Agent 開發 Quickstart

## 1. 執行現有測試

```powershell
python -m unittest discover -s tests -v
```

## 2. 寫入並索引記憶

```powershell
python -m memlite.retrieval_cli --db data/retrieval-demo.db remember --scope demo --type semantic --content "回答時請使用繁體中文"
python -m memlite.retrieval_cli --db data/retrieval-demo.db remember --scope demo --type semantic --content "部署環境使用 Docker"
```

## 3. 查看可解釋的 retrieval trace

```powershell
python -m memlite.retrieval_cli --db data/retrieval-demo.db retrieve --scope demo --query "我偏好使用哪一種中文？"
```

輸出會包含：

- 所有 vector candidates。
- similarity、recency、importance、confidence 與 frequency。
- pollution penalty 與 final score。
- 是否被選入 context。
- 被拒絕時的原因。
- 預估占用 token。

## 4. 執行 deterministic baseline

```powershell
python -m memlite.benchmark_cli --summary-only
```

這個 baseline 不代表真正 embedding model 的語意能力。它的用途是建立零成本、固定結果的比較基準；後續接 Chroma 與真實 embedding 時，使用相同 dataset 比較 Precision、Recall、MRR 與 latency。

## 5. 建議閱讀順序

1. `memlite/models.py`
2. `memlite/storage/sqlite.py`
3. `memlite/embeddings/deterministic.py`
4. `memlite/vector/sqlite.py`
5. `memlite/policies/retrieval.py`
6. `memlite/engine.py`
7. `memlite/evaluation/retrieval_benchmark.py`

