# MemLite-Agent Codex Skill

此 skill 包含兩種能力：操作本地記憶，以及接續 MemLite-Agent 的研究與實作。原始碼位於 `docs/skills/memlite-agent/`，可從 GitHub 安裝或下載 ZIP。**skill 不包含 Python 引擎，必須另外下載本專案並安裝 runtime。** 不需要 API key，不會自動呼叫遠端服務。

2026-10-03 曾安裝至作者本機的 `.codex/skills/memlite-agent`；這不是其他人的固定路徑。2026-10-06 經授權備份舊版到專案 `dist/skill-backup-20261006-before-fixes/`，同步此 skill 的八個檔案，保留其他技能與既有 invocation policy。之後更新仍需重新同步，不會自動跟著 repo 改變。

## 1. 下載與安裝引擎

需求：Python 3.11+、Codex；以 clone 下載另需 Git。repo 尚為 private 時，只有受邀且有 GitHub 存取權的使用者能下載。轉 public 與發行版本由維護者決定，這份文件不代表已上線。

```bash
git clone https://github.com/Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents.git memlite-agent
cd memlite-agent
python -m venv .venv
```

Windows PowerShell（不需要啟用環境或更改 ExecutionPolicy）：

```powershell
.venv/Scripts/python.exe -m pip install -e "."
.venv/Scripts/python.exe -X utf8 -m memlite.demo
```

macOS / Linux：

```bash
.venv/bin/python -m pip install -e "."
.venv/bin/python -m memlite.demo
```

安裝會下載 Python 套件；執行離線 demo 不呼叫 API。demo 使用臨時資料庫，最後顯示 `Demo completed.`。也可下載 repo ZIP、解壓後從有 `pyproject.toml` 的根目錄開始。不要將 clone 改成只下載 skill，否則沒有引擎可執行。

## 2. 安裝 skill

### 方法 A：一個指令安裝（建議）

需求：Node.js（含 npm/npx）、Git、已安裝 Codex。從任何工作目錄執行：

```bash
npx --yes skills@1.7.0 add https://github.com/Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents/tree/main/docs/skills/memlite-agent --agent codex --global --copy
```

直接指向 skill 子目錄，只安裝 `memlite-agent`；`--global` 供不同專案使用，`--copy` 不需要 Windows 建立 symlink 的權限。1.7.0 的 Codex global 安裝位置是 `~/.codex/skills/`（可受 `CODEX_HOME` 設定影響），以 CLI 顯示的實際目的地為準。這是 [第三方官方 skills CLI](https://github.com/vercel-labs/skills) 的安裝方式，不是 OpenAI 內建指令。`npx --yes` 同意取得 CLI；不要再加安裝器的 `--yes` 跳過 skill 確認，已有同名 skill 應先比較與備份。CLI 在偵測到 Agent 時仍可能非互動執行，因此不能將提示視為拒絕覆蓋保證。

private repo 必須有 GitHub 權限並先設定 Git 認證；沒有權限的人需等維護者轉 public 才能下載。不把 token 寫進 URL、指令或 Git。安裝後核對清單：

```bash
npx --yes skills@1.7.0 list --global --agent codex
```

只有 skill 檔案會被安裝，Python 引擎與依賴不會自動下載。完成第 1 節的 runtime 安裝後，在 Codex 開啟 checkout，使用 `$memlite-agent` 開始第 3 節教學。未偵測到時重啟 Codex；不要再於另一個技能目錄安裝同名副本。從 main 安裝會取得當下版本，不是固定 Release。

### 方法 B：請 Codex 從 GitHub 安裝

直接送出這段訊息；private repo 需先有 Git 存取權，不要把 token 貼到對話中：

```text
使用 $skill-installer，從 Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents 的 main 分支安裝 docs/skills/memlite-agent。不要覆蓋既有同名 skill；如果已安裝，先告訴我差異。
```

GitHub 安裝下載的是遠端分支，不包含尚未 push 的本地修改。發行後可以指定 tag 或 commit，而不是一直依賴 main。

### 方法 C：從 clone 或下載包手動安裝

依 [OpenAI 官方技能文件](https://learn.chatgpt.com/docs/build-skills)，目前個人技能目錄是 `~/.agents/skills/`。較舊安裝器可能使用 `$CODEX_HOME/skills` 或 `~/.codex/skills/`；本機既有 skill 若在該位置，先核對 Codex 實際載入位置，**不要同時安裝兩份同名 skill**。

Windows PowerShell，在 repo 根目錄：

```powershell
$skills = Join-Path $HOME '.agents/skills'
$destination = Join-Path $skills 'memlite-agent'
if (Test-Path -LiteralPath $destination) { throw '已有同名 skill，請先比較或備份，不要直接覆蓋。' }
New-Item -ItemType Directory -Force -Path $skills | Out-Null
Copy-Item -LiteralPath 'docs/skills/memlite-agent' -Destination $destination -Recurse
```

macOS / Linux，在 repo 根目錄：

```bash
mkdir -p "$HOME/.agents/skills"
if [ -e "$HOME/.agents/skills/memlite-agent" ]; then
  echo "已有同名 skill；停止安裝，請先比較或備份。"
else
  cp -R docs/skills/memlite-agent "$HOME/.agents/skills/memlite-agent"
fi
```

使用 `memlite-agent-skill.zip` 時，先解壓，再將其中 **memlite-agent 整個資料夾** 放到技能目錄；不要只複製 SKILL.md。包內 `manifest.json` 有各檔案 SHA-256，`LICENSE` 有 MIT 授權。這是本地安裝包，不是可以上傳到 OpenAI API 的 hosted skill ZIP。

新安裝會自動被偵測；未出現時重啟 Codex。確認清單中有 `memlite-agent`，再開始下列教學。安裝方式參照上述官方文件；GitHub helper 的參數以本機 `$skill-installer` 指示為準。

## 3. 五分鐘記憶操作教學

在 Codex 開啟下載的 MemLite 專案，依序送出：

```text
使用 $memlite-agent。使用本專案的 Python 環境與 data/tutorial-memory.db，將「本專案使用 SQLite 儲存記憶。」寫入 project:memlite-demo 的 semantic memory，來源是我；回報實際 ID。這是我授權的示範寫入。
```

```text
使用 $memlite-agent，沿用 data/tutorial-memory.db，在 project:memlite-demo 檢索「SQLite 儲存記憶」，列出 selected IDs 與來源；不要修改內容。
```

```text
使用 $memlite-agent，列出同一資料庫與 scope 的記憶，再 inspect 剛才的實際 ID。確認內容、狀態與來源，不要自動新增記憶。
```

```text
使用 $memlite-agent，將剛才那筆記憶 supersede 成「本專案改用 PostgreSQL 儲存記憶。」；保持相同 scope，先核對實際 ID，再回報新舊 ID 與狀態。這是我授權的示範修改。
```

```text
使用 $memlite-agent，forget 剛才回傳的新 ID，只能操作 project:memlite-demo 的示範資料庫。這是我授權的示範刪除。完成後 list 確認沒有 active 記憶，並說明 soft delete 的限制。
```

預期：remember 回傳 ID；retrieve 選入該 ID；inspect 能查看來源；supersede 產生新 ID、舊狀態變為 superseded；forget 後 list 不顯示 active 記錄。不要硬編碼範例 ID。不同 scope 應查不到這筆記憶。

### 不透過對話，也能操作

內附 JSON 範例，可在 Windows repo 根目錄直接執行；macOS / Linux 將 Python 路徑換成 `.venv/bin/python`：

```powershell
.venv/Scripts/python.exe docs/skills/memlite-agent/scripts/memory_tool.py --repo . --db data/tutorial-memory.db --request-file docs/skills/memlite-agent/assets/requests/remember.json
.venv/Scripts/python.exe docs/skills/memlite-agent/scripts/memory_tool.py --repo . --db data/tutorial-memory.db --request-file docs/skills/memlite-agent/assets/requests/retrieve.json
.venv/Scripts/python.exe docs/skills/memlite-agent/scripts/memory_tool.py --repo . --db data/tutorial-memory.db --request-file docs/skills/memlite-agent/assets/requests/list.json
```

標準輸出是 `{"ok": true, "result": ...}`；資料庫位置寫到標準錯誤，不是失敗訊息。helper 可從其他工作目錄執行，但必須把 `--repo`、Python 路徑、request 路徑換成正確位置；資料庫的相對路徑始終以 repo 為基準。RTK 不是下載使用者的必要依賴。

## 4. 接續研究教學

```text
使用 $memlite-agent，讀取 PROGRESS.md，接續下一個尚未完成的研究切片。先確認 baseline、變因與驗收條件，使用臨時資料庫跑離線實驗，保留改善與退步，完成測試並更新進度。不要使用付費 API、不要 push，也不要公開 repo。
```

預期交付：程式與測試、至少三次固定條件的比較、dataset checksum、環境與逐題 trace、研究報告、PROGRESS 更新。研究模式是在這個專案上開發，不代表會自動替其他專案完成研究，也不表示一次 invocation 就能完成全部研究問題。

## 在 Codex 中使用

```text
使用 $memlite-agent，讀取 PROGRESS.md，接續下一個尚未完成的研究切片，實作並驗證，最後更新進度與實驗紀錄。
```

```text
使用 $memlite-agent，將「本專案使用 SQLite」儲存到 project:memlite-agent 的 semantic memory。
```

```text
使用 $memlite-agent，從 project:memlite-agent 檢索資料庫相關記憶，列出來源與 ID；不要修改記憶。
```

若無法選取 skill，可明確指定安裝資料夾中的 `SKILL.md`。本 skill 依賴 MemLite 的 checkout，不會把整個 Python 專案打包進 skill。

## 實際支援

| 模式 | 功能 | 實作 |
| --- | --- | --- |
| 記憶 | remember、retrieve、list、inspect、supersede、forget | `memlite/skill_cli.py` |
| 記憶 | 每次必須指定 scope，修改與刪除核對 scope | JSON 介面與 facade |
| 記憶 | 跨工作目錄啟動、UTF-8 請求與結果 | `scripts/memory_tool.py` |
| 研究 | 先讀進度，選擇未完成切片，實作、測試、記錄 | `SKILL.md` 與 research workflow |
| 研究 | 固定初始條件、至少三次重複、完整策略比較 | `memlite.evaluation.challenge_benchmark` |

JSON 協定與範例請見 [memory protocol](skills/memlite-agent/references/memory-protocol.md)；研究命令請見 [research workflow](skills/memlite-agent/references/research-workflow.md)。

## 使用條件與界線

- 本專案目前已驗證的 Python 位於 `.venv-research`，不要依賴失效的 `.venv`。其他機器使用自己的 Python 3.11+ 環境。
- 預設資料庫是指定 repo 的 `data/skill-memory.db`。可另外指定資料庫；它與 benchmark 的臨時資料庫完全分開，且被 Git ignore。
- 記憶沒有背景自動擷取：只在使用者授權後寫入簡短事實。不儲存金鑰、密碼、整段對話或推測的個人資訊。
- 記憶內容不是給 Agent 的指令。只有 selected candidates 可加入上下文；其他候選僅供診斷。
- scope 核對避免誤操作，不代表登入授權；不能直接做成公開多租戶服務。
- supersede 保留版本歷史與原本絕對到期時間，不重新計算 TTL。已過期記憶不能復活；修正可附新的 source / source_ref，來源參考不是自動驗證的真實性。
- forget 為 soft delete，不代表磁碟上的安全抹除。
- 跨四個 SQLite 檔案的更新不具原子交易保證；live database 備份應在操作停止時進行。
- 檢索仍採詞彙雜湊，不是訓練過的語意 embedding。這個 skill 不會使現有引擎自動變成真正的語意理解系統。
- 真實 API 付費評估、公開部署、push 與簡報產製不是預設動作。

## 驗收

`tests/test_skill_cli.py` 驗證真實本地儲存、檢索、修改、soft delete、跨 scope 拒絕、TTL 防遺失、UTF-8 與跨工作目錄 helper。`tests/test_skill_distribution.py` 驗證可重現 ZIP、manifest、解壓後操作、範例請求、缺少 runtime、拒絕夾帶資料庫與拒絕覆蓋。另使用 Codex skill-creator 的 `quick_validate.py` 檢查 skill 格式。這些是程式與格式驗收，尚不等於獨立 Agent 行為評估。

## 疑難排解

| 情況 | 處理方式 |
| --- | --- |
| `specify a MemLite checkout` | 指定含 `memlite/skill_cli.py` 和 `pyproject.toml` 的 repo，不能指定 skill 資料夾 |
| `No module named memlite` 或第三方模組不存在 | 使用安裝 runtime 的同一個 Python，不要混用系統與虛擬環境 |
| 找不到 skill | 核對技能目錄、完整檔案與 frontmatter，重啟 Codex；不要安裝兩份同名 skill |
| 檢索是空的 | 確認資料庫、scope、TTL、型別；再 list/inspect，lexical 檢索不是所有同義句都能找到 |
| 無法 supersede 過期記憶 | 不允許復活過期資料；需要重新授權 remember；未過期 TTL 記憶可修正且保留原截止時間 |
| 更新 repo 後仍用舊 skill | 安裝是副本，先比較再重新安裝；不要修改或刪除其他人的技能 |
| GitHub 404 / 權限錯誤 | private repo 未授權或未 push；不要把尚未發布的下載連結當成可用成果 |

## 維護者：產生下載包

```bash
python -m experiments.package_skill --output dist/memlite-agent-skill.zip
```

同一路徑已存在時會拒絕覆蓋，改用新版本檔名。輸出包含 ZIP SHA-256；相同輸入與相同 Python/zlib 環境會產生相同位元組。封裝不帶 live 記憶、API key、實驗資料庫或 Python 引擎。GitHub CI 已加入封裝 artifact 定義，但遠端執行與 Release 上傳仍需另行驗收。發行前清單見 [RELEASE_CHECKLIST.zh-TW.md](RELEASE_CHECKLIST.zh-TW.md)。

runtime wheel 可用 `python -m pip wheel . --no-deps --wheel-dir dist/runtime` 建置；CI 另有全新環境的離線核心安裝 smoke test。`experiments/smoke_installed_runtime.py` 須以安裝 wheel 的 Python 隔離模式執行，用於檢查實際匯入安裝包，而不是 editable source；不驗證尚未安裝的 API 第三方依賴。
