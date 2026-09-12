# AiAgent 節點：隔離設計與移植性

> 2026-08-30 從 `CLAUDE.md` 移出（106 行）。
> **改 `ai_agent_handler.py` 之前整份讀完**——prompt 裡放的是攻擊者可控的資料，
> 隔離不是選配。用量與配額見 `AI_NODE_USAGE_QUOTA_SPEC.md`，
> 對外部署需求見 `docs/install/ai_node.md`。

---

## AiAgent 節點：`claude -p` 是 agent 不是 API，一定要關掉自訂與工具（2026-08-20）

節點型別 `AiAgent`，handler
`modules/form_workflow/services/node_handlers/ai_agent_handler.py`。
它把流程資料交給本機 `claude -p` 分析，結果寫流程變數並可插一筆
`fw_approval_records`（`action='ai_note'`、`approver_secure_code=NULL`）。

**`claude -p` 不是「送字串到雲端再回傳」，是完整的 agent**
（回應 envelope 有 `num_turns`）。預設狀態下它會用工具、讀
`$HOME/.claude/CLAUDE.md`、繼承呼叫者的**全部 MCP server**
（beak_broodnest / chrome-devtools / Google Drive / SendMessage…）。
prompt 裡放的是攻擊者可控的資料，所以隔離不是選配。

**用原廠的兩個參數就夠，不要自己搭黑名單**：

```
--safe-mode     停用全部自訂（CLAUDE.md、skills、plugins、hooks、MCP servers、
                custom commands/agents…），一個參數全包
--tools ""      停用全部內建工具
```

**`--tools` 與 `--allowedTools` 是兩個不同參數。**
`--allowedTools ""` 會被當成「未指定」而**放行 Bash/Edit/Write**（實測踩過）；
`--tools ""` 才是明確的全部停用。寫錯這個等於完全沒設防，而且從回應看不出來。

2026-08-20 最嚴苛條件實測（真實 HOME、cwd 直接指在專案根目錄）：
`NO_CLAUDEMD` / `NO_MCP` / `NO_TOOLS`，要它建檔案時檔案不會出現。

**驗證一定要看副作用，不能問它「你有什麼工具」。**
實測中它回答「我將建立這個檔案」，但檔案根本沒出現——自我報告不可信。

其餘設計：cwd 用 `tempfile.TemporaryDirectory()` 每次動態建（無需預先建目錄）；
CLI 路徑走 `AI_NODE_CLI_PATH` 環境變數 → `shutil.which('claude')` → `'claude'`，
**每次執行時解析**（`resolve_cli_path()`，不在 import 時定死，否則長駐的 executor
事後換路徑永遠不生效）。**沒有任何要手動建立的目錄**，換機器直接可跑。

**2026-08-21 起這四件是硬規則（移植性修正，commit `84b381ee`）**：

- **CLI 路徑不從節點 config 取。** 節點設定存在 `fw_workflow_templates.graph`，
  而 graph 可用 PUT API 改寫——允許 `cli_path` 等同讓能編流程的人以 executor
  的 OS 帳號執行任意程式。原本的 `get_config_value('cli_path')` 已移除，
  **不要為了「方便測試」加回來**
- **env 是白名單不是全剝**（`build_subprocess_env()`）。只剝平台秘密，
  放行 `ANTHROPIC_*` / `CLAUDE_CODE_USE_*` / proxy / CA；`AWS_*` 與 GCP 憑證
  只在對應的 `CLAUDE_CODE_USE_BEDROCK` / `_VERTEX` 啟用時才放行。
  全剝的舊寫法會讓「使用者自己已備妥的 API key、企業 proxy、內部 CA」
  一律靜默失效——那是本專案擋住他，不是他的環境問題
- **執行前偵測 CLI 是否支援 `--safe-mode` 與 `--tools`**
  （`_ensure_cli_supports_isolation()`）。看 `--help` 輸出而**不是比版本號**
  （不知道確切哪一版引入，比版本會誤判）。fail-closed；**成功才快取**，
  失敗不快取，讓部署者升級 CLI 後不必重啟 executor
- **錯誤訊息要帶 envelope 的 `result`**。未登入時 CLI 回
  `stop_reason=stop_sequence`、真正原因 `Not logged in · Please run /login`
  在 `result` 裡。只取 stop_reason 的舊寫法讓部署者完全看不出該做什麼

對外部署需求（其他人裝這套時要準備什麼）寫在 **`docs/install/ai_node.md`**
（會推上 GitHub），`.env.example` 有對應的註解段。改 handler 的行為時記得同步。

**但 `AI_NODE_CLI_PATH` 在本機是非設不可的**（2026-08-20 第一次真的經由 executor
跑流程才發現）：`beakplatform-dev-executor.service` 的 unit 寫死

```
Environment=PATH=/opt/BeakPlatform-dev/venv/bin:/usr/local/bin:/usr/bin:/bin
```

不含 `~/.local/bin`，所以 `shutil.which('claude')` 找到的是 root 裝的舊版
`/usr/local/bin/claude`（2.0.27，**沒有 `--safe-mode`**），節點每次都失敗，
log 是 `AI CLI 退出碼 1: error: unknown option '--safe-mode'`。
`.env` 已加 `AI_NODE_CLI_PATH=/home/ethan/.local/bin/claude`（2.1.237）。

這件事的通用教訓：**在互動 shell 裡驗證過的外部指令，不等於 executor 跑得動**——
systemd unit 的 PATH 與你的 shell 不同。凡是節點會呼叫外部程式，
驗收一定要真的經由 executor 跑一次流程，不能只在 `venv/bin/python -c` 裡驗。
（舊版 CLI 的行為是 fail-closed：參數不認得就整個退出，不會退化成沒有隔離的執行。）

**流程變數是扁平的，`${v.ai.verdict}` 取不到值**。AiAgent 除了 `result_var`
本身（物件）之外，另外攤平寫出 `<result_var>_verdict` / `_score` / `_ok` /
`_rule_hits` / `_note`，Branch 條件要判 verdict 只能用這些
（與 SysSqlExecutor 的 `<result_var>_<欄位>` 同一套命名）。

**AI 一律沒有寫入權**：它只出文字，所有寫入由 handler 做。規則層的
injection 偵測不經過 AI、直接生效，系統警示由 handler 在 AI 輸出**之後**拼接，
AI 移除不掉。改這個檔案前先讀檔頭那段安全設計說明。

**改 handler 後 executor 要重啟才認得**（`beakplatform-dev-executor` 是獨立進程）。

**用量記錄與配額已上線（PF-139，2026-08-21）**，定版文件
`dev-notes/AI_NODE_USAGE_QUOTA_SPEC.md`，動這塊之前整份讀完。四件猜不到的：

- **`total_cost_usd` 是全部模型的總和，但 top-level `usage` 的 token 只算主模型。**
  即使只指定一個 `--model`，envelope 仍可能出現第二個模型（CLI 用 haiku 做輔助作業）。
  實測樣本：sonnet-5 $0.0108（2/270 tokens）＋ haiku-4-5 $0.001421（1331/18 tokens）
  ＝ `total_cost_usd` 0.012221。**寫 parser 不要假設 `modelUsage` 只有一個 key**
- **成本是 API 牌價的等值估算，不是實際扣款**（訂閱制下仍以牌價估算）。
  對外文案一律寫「估算成本」，不要寫成費用或帳單
- **配額超限一律走 error 邊，不看節點的 `on_error`** —— 那代表節點根本沒被允許執行，
  靜默略過會讓簽核者誤以為 AI 已經看過
- **流程引擎對回 error 的節點重試到 `max_retries=3`**（`FwNodeExecutionQueue.fail()`
  沒有不可重試的分支），所以 blocked 記錄依 `node_queue_secure_code` 去重，
  一個節點被擋只記一次。**不要為了「讓計數變準」而拿掉去重**

配額與用量的**唯一實作**是 `modules/form_workflow/services/ai_usage_service.py`
（含 `pg_advisory_xact_lock` 防併發穿透、日界月界依企業時區換算）。
**禁止**在 API、前端或其他 handler 自行組配額 SQL 或讀寫 `ai_node_*` 設定 key。
管理頁在 `/forms/ai-usage`（`form_workflow.admin`）。
