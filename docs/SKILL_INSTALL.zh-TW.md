# MemLite-Agent Skill 下載包

本 ZIP 是本地 Codex skill，不包含 Python 記憶引擎，也不是 hosted API upload 的 skill ZIP。

不使用 ZIP，也可在安裝 Node.js 與 Git 後，一個指令直接從 GitHub 安裝：

```bash
npx --yes skills@1.7.0 add https://github.com/Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents/tree/main/docs/skills/memlite-agent --agent codex --global --copy
```

參數見 [官方 skills CLI](https://github.com/vercel-labs/skills)。已有同名 skill 請先備份／比較，CLI 不保證拒絕覆蓋。private repo 需有 GitHub 存取權與 Git 認證。此指令只安裝 skill，仍需以下第 2 步的 Python 引擎；不要把它當成完整 runtime 安裝。只採用一種安裝方式，避免同名副本。

1. 將包內 `memlite-agent/` 整個資料夾安裝到 Codex 載入的個人技能目錄。依現行 [OpenAI 官方文件](https://learn.chatgpt.com/docs/build-skills)，個人目錄為 `~/.agents/skills/`；較舊環境可能使用 `~/.codex/skills/`。已有同名 skill 時先比較與備份，勿安裝兩份或直接覆蓋。
2. 另外下載 [MemLite 專案](https://github.com/Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents)，以 Python 3.11+ 建立虛擬環境，在 checkout 根目錄執行 `python -m pip install -e .`。安裝需取得套件，但離線記憶操作不呼叫 API。
3. 在 Codex 開啟 checkout，確認 `memlite-agent` 可選取；未出現時重啟。執行時使用該 checkout 已安裝的 Python，並明確指定 repo、scope 與示範資料庫。

第一次使用可送出：

```text
使用 $memlite-agent，使用此專案的 Python 環境，在 data/tutorial-memory.db 將「本專案使用 SQLite 儲存記憶。」寫入 project:memlite-demo 的 semantic memory，回報實際 ID。這是我授權的示範寫入。
```

接著檢索同 scope 的「SQLite 儲存記憶」，核對 selected ID 與來源。沒有授權不會記錄對話；忘記是 soft delete，不是安全抹除。scope 不是登入授權，這是本地工具，不應直接公開資料庫 API。

完整的跨平台安裝、修正／刪除教學與研究模式，見 [GitHub 使用教學](https://github.com/Ayak444/A-Lightweight-Memory-Management-and-Caching-System-for-LLM-Agents/blob/main/docs/SKILL_USAGE.zh-TW.md)。repo 仍為 private 或尚未 push 時，需要存取權且遠端可能還沒有最新檔案。

離線協定見 [memory protocol](memlite-agent/references/memory-protocol.md)，研究程序見 [research workflow](memlite-agent/references/research-workflow.md)；後者引用的研究檔案位於 runtime checkout。`manifest.json` 列出每個內容檔案的 SHA-256；checksum 用於完整性核對，不是維護者的數位簽章。授權見包內 `LICENSE`。
