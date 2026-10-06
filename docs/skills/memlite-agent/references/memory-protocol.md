# 本地記憶協定

最低需求：Python 3.11+ 與 MemLite checkout。使用該專案可正常運作的 Python 執行 skill 的 `scripts/memory_tool.py`；所有相對資料庫路徑以 `--repo` 為基準，request 檔案路徑則以目前工作目錄為基準。UTF-8 請求可先放在 workspace 暫存檔，不要在 shell 字串內拼接使用者內容。

```powershell
python "<skill-root>/scripts/memory_tool.py" --repo "<memlite-checkout>" --db "data/skill-memory.db" --request-file "request.json"
```

也可使用 `python -m memlite.skill_cli --db <database>` 從標準輸入送入 JSON。輸出是 UTF-8 JSON：`{"ok":true,"result":...}`；失敗回傳 `ok:false`、error 與非零 exit code。

`python` 需指向 checkout 的已安裝環境；本機若有 RTK 指示，照該 workspace 規則加上前綴，其他使用者不需要安裝 RTK。內附 `assets/requests/remember.json`、`retrieve.json`、`list.json` 可直接配合 `--request-file` 使用；示範 scope 是 `project:memlite-demo`，請使用獨立的 demo 資料庫。

每個請求必須包含 `operation` 與非空白 `scope`：

```json
{"operation":"remember","scope":"project:memlite-agent","type":"semantic","content":"本專案使用 SQLite 儲存記憶。","source":"user","source_ref":"PROJECT_GUIDE.md"}
```

```json
{"operation":"retrieve","scope":"project:memlite-agent","query":"本專案使用哪種資料庫？","types":["semantic"]}
```

```json
{"operation":"list","scope":"project:memlite-agent","limit":20}
```

```json
{"operation":"inspect","scope":"project:memlite-agent","memory_id":"實際回傳的 ID"}
```

```json
{"operation":"supersede","scope":"project:memlite-agent","memory_id":"實際回傳的 ID","content":"確認後的新事實","source":"user","source_ref":"確認過的設計紀錄"}
```

```json
{"operation":"forget","scope":"project:memlite-agent","memory_id":"實際回傳的 ID"}
```

remember 可選：`type` working/episodic/semantic、`source` user/llm/tool/system、`importance` 與 `confidence` 0–1、正整數 `ttl_seconds`。list 的 limit 為 1–1000。retrieve 的空 `types:[]` 代表不取任何記憶；省略則不限類別。

只取 `selected_memory_ids` 對應的 candidates。檢索採 deterministic lexical hash，並非訓練過的語意 embedding；換句話說可能漏掉同義改寫，不能據此聲稱「已理解」所有記憶。

inspect 能查看同 scope 的舊版本；supersede/forget 只接受 active ID。跨 scope ID 會被拒絕。supersede 保留原本的絕對到期時間，不重啟 TTL；過期記憶不能替換成永久記憶，需另行授權建立新記憶。修正可附 `source`（預設 user）與 `source_ref`（省略時 null），不自動沿用可能已過期的來源；參考位置不是經過驗證的證據。範圍檢查不是登入授權；不要把這個 CLI 直接當作公開多租戶 API。

忘記是 soft delete，不是機密資料安全抹除。四個 SQLite 檔案不具跨檔交易原子性；異常中斷後可用 `memlite.retrieval_cli reindex` 重建該 scope 的向量索引。不要把 live 記憶資料庫加入 Git，也不要將測試資料寫進 live 資料庫。
