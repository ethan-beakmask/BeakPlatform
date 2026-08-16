# 交接：下一個 Session 從這裡開始

> 建立：2026-07-08 03:36（P3 完成當晚）
> 用法：新 session 開場先讀本檔，再依優先序動工。做完的項目請從本檔刪除或標記。

## 現況快照（2026-07-11 更新）

- P1 / A-1 / P2 / P3 已全部 push（Forgejo + GitHub 過濾推送皆完成），工作區乾淨
- 規格與進度：`dev-notes/API_KEY_TRIGGER_SPEC.md`（P1/P2/P3 狀態都在 §階段規劃 與 §7）
- push 狀態確認指令：`git log origin/main..HEAD --oneline`（空 = 都推了）

## 已驗收（2026-07-11）

- **P3 ApiKeyAction E2E**：用戶以自建流程「API_KEY測試」驗證 ApiKeyAction 功能通過，驗收完成
  - 重驗方式：送單觸發「API_KEY測試」流程即可；handler 在
    `modules/form_workflow/services/node_handlers/api_key_action_handler.py`
  - 當時的 10/10 單元測試是臨時腳本、未入版控；正式重驗以 E2E 為準
- **設計器「安全管控」分類**：用戶目視確認，驗收完成

## BBN 知識原子取用方式（本檔引用的 #編號都這樣拿）

MCP 工具 `mcp__beak_broodnest__note_get(atom_id=<編號>)`。本檔相關原子：
- **#4608** DevTools CDP 鏈路部署程序（權威）
- **#4823** 9222 連通排查現況
- **#4609** F12 除錯標準 SOP
- **#4607** BeakDevF12 專案（已 DEPRECATED，勿照做）

自動化登入：**此處原本的帳密範例（`admin-ethanyu@beluga.com` / `ApiKeyTest2026`）
已於 2026-08-03 實測失效（401），照打會逼近帳號鎖定**。
一律改走 `/dev/quick-login`，指令見 `CLAUDE.md` 的「開發測試登入」段。

## 待辦（依優先序）

### 2. 突發保護 A/B/C

規格：`dev-notes/handoff_burst_protection_ABC.md`（起手檔案、schema、驗證計畫都在規格內）。

**A 狀態更正（2026-07-11 實測）**：先前交接寫「A 已完成」，但
`systemctl show beakplatform-dev-executor` 顯示 `MemoryMax=infinity`、
unit 檔（`/etc/systemd/system/beakplatform-dev-executor.service`）無任何資源限制、無 drop-in
→ **A 實際未生效，需重做**。屬 OS 層級變更，需用戶現場同意 + 先備份 unit 檔。

- B（executor 並發封頂）：改 `backend/workflow_executor_main.py`，
  `EXECUTOR_MAX_CONCURRENT` 環境變數預設 8，驗證 `pgrep -c node_runner` <= N
- C（intake 事件聚合）：新表 `od_intake_aggregations` + 改
  `modules/open_defense/services/intake_service.py` 的 `process_event()`，
  完成後更新 `dev-notes/manifests/mod-open-defense.yaml`
- migration 慣例：`scripts/migrations/` 下取現有最大編號 +1 的 `.sql` 檔（現到 080），
  用 psql 套用：`PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -f <檔案>`
- 動工前必讀規格全文（schema、window 策略、抽樣、驗證計畫都在裡面，本節只是索引）

### 3. DevTools 9222 連通排查（用戶主導，見下節）

### 4. 下一版本週期的遺留清理（勿現在做，啟動條件：用戶明確宣布進入下一版本週期）

~~刪 `od_intake_keys` 表 + `/open-defense/intake-keys` 頁 + `intake_key_service.py`~~
已完成（2026-08-17，migration 105；規格 §7 P2 節有記）。

## DevTools（chrome-devtools-mcp）啟動與測試 SOP

完整部署程序在 **BeakBroodNest atom #4608**（那份才是權威，本節是速查）。
BeakDevF12 專案本身已廢棄（atom #4607），但 9222 CDP 鏈路是現行方案，沒有棄用。

架構：Windows(192.168.0.10) CDP Chrome listen 127.0.0.1:9222 → netsh portproxy 轉 LAN
→ Ubuntu 端 chrome-devtools-mcp `--browserUrl=http://192.168.0.10:9222`（user scope，已註冊）。

### 2026-07-11 03:50 已解決（解決紀錄在 BBN atom #4823）

根因：CDP Chrome 用錯 shell 語法沒掛上 CDP + portproxy 規則在但 iphlpsvc 未綁定
（`net stop iphlpsvc && net start iphlpsvc` 後生效）。MCP 工具實測全通。
開機自動復原已由 **BeakDevF12 自癒工具**解決（2026-07-11 部署，程式在 `/opt/BeakDevF12/`，
Windows 端排程任務 `BeakDevF12-Repair` 每 5 分鐘自癒，詳見 atom #4823 後段）。
待用戶下次重開機後最終驗收（待辦原子 #4826）：
Ubuntu 端 `curl -m 5 http://192.168.0.10:9222/json/version` 拿到 JSON 即過（登入後最慢 5 分鐘）。
失敗時請用戶在 Windows 跑 `C:\BeakDevF12\beakdevf12.ps1 status`（四環節哪環斷一目了然）、
看 log `%LOCALAPPDATA%\BeakDevF12\beakdevf12.log`，手動修復 `beakdevf12.ps1 repair`（需管理員）。

以下排查表保留供未來斷線時使用：

| 癥狀 | 含義 | 檢查 |
|------|------|------|
| timeout | 封包被丟：防火牆擋、或 portproxy 沒 listen 且防火牆丟 SYN | 見下 |
| refused | 有到機器但沒 listener：portproxy 消失 | `netsh interface portproxy show all` |

Windows 端排查順序（管理員 PowerShell）：
```powershell
# 1. Chrome 是否用對參數啟動（必須是 CDP 專用 profile，不是日常 Chrome 按 F12）
#    必要參數：--remote-debugging-port=9222 --remote-allow-origins=*
#              --user-data-dir="%LOCALAPPDATA%\Chrome-CDP-Profile"
netstat -ano | findstr :9222   # 應看到 127.0.0.1:9222 (Chrome) 與 192.168.0.10:9222 或 0.0.0.0:9222 (portproxy)

# 2. portproxy（重開機會消失，最常見原因）
netsh interface portproxy show all
netsh interface portproxy add v4tov4 listenaddress=192.168.0.10 listenport=9222 connectaddress=127.0.0.1 connectport=9222

# 3. 防火牆規則是否還在/被停用
Get-NetFirewallRule -DisplayName "Chrome CDP from BeakUbuntu"

# 4. Windows 本機自測
curl http://192.168.0.10:9222/json/version   # 拿到 JSON 才算 Windows 端 OK
```

Ubuntu 端驗證：
```bash
curl -m 5 http://192.168.0.10:9222/json/version      # 拿到 JSON 即通
# 通了之後 MCP 工具（mcp__chrome-devtools__*）即可直接用，不用重註冊
```

## 已處理（2026-07-11）

**/upcom 交接品質改善**：已完成，`~/.claude/commands/upcom.md` 改為五步驟：
知識存檔 → 建待辦 → 交接品質（事實歸位 CLAUDE.md / 待辦附驗證過的指令 / codex 冷讀審核）
→ 摘要 → commit+push（依專案 push 規範）。冷讀首選
`codex exec --sandbox read-only`（本機 codex-cli 已登入可用），失敗退回 Claude subagent。

## 本 session 順手修掉的既有 bug（已 commit，供追溯）

1. `wf-node-alert-broadcast.js` 角色/部門 fetch 前綴錯誤（404 被 catch 吃掉）→ `/api/workflows/data/`
2. `workflow_node_definitions.icon` 23 筆殘留舊前綴 `/bp/static/` 導致 palette 圖示全破圖
   → DB 正規化 + API 以 `request.script_root` 動態補前綴
3. node-definitions category_map 缺「安全」→ DecisionWriter/ApiKeyAction 掉進「基本節點」
   → 前後端補 `security`／「安全管控」分類
