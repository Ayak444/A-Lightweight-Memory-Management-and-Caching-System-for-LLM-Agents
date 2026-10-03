# ADR 0001: 使用 SQLite 作為主要事實來源

## Context

MemLite-Agent 同時需要結構化 metadata 與向量索引。兩份儲存可能因網路、程序中斷或 provider 錯誤而不一致。

## Decision

SQLite 保存完整 `MemoryItem`、狀態與關係並作為 source of truth。Vector backend 只保存 embedding 與查詢所需的最小 metadata，且必須能從 SQLite 重建。

## Consequences

- 記憶內容、版本與來源可以直接檢查和備份。
- Vector index 損壞時不會失去主要資料。
- 跨儲存寫入需要失敗紀錄與 reindex；後續可加入 outbox。

