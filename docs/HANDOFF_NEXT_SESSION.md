# 交接：下一個 Session 從這裡開始

> 建立：2026-07-08 03:36（P3 完成當晚）
> 用法：新 session 開場先讀本檔，再依優先序動工。做完的項目請從本檔刪除或標記。

## 現況快照

- 本機 main 有 7 個 commit 未 push（P1 / A-1 / P2 / P3 全部），**用戶未下 push 指令前不要 push**
- 最新 commit `0eca4c90`：P3 ApiKeyAction 流程節點完成，handler 單元測試 10/10 PASS
- 用戶已目視確認設計器 palette「安全管控」分類與 ApiKeyAction 節點面板正常
- 規格與進度：`docs/API_KEY_TRIGGER_SPEC.md`（P1/P2/P3 狀態都在 §階段規劃 與 §7）

## 待辦（依優先序）

### 1. ApiKeyAction 真實 executor E2E（收尾 P3）

Handler 已用假 queue_item 測過 10 項情境，缺的是走真實背景 executor 的一次完整執行。SOP：

1. 登入 `admin-ethanyu@beluga.com` / `ApiKeyTest2026`（JSON login 可自動化，見下方範例）
2. 設計器 `/forms/workflows/<sc>` 找一條測試流程（如「弱點追蹤」`ktKgP3thmLF4coERXvUaYg`），
   或建新流程：Start → ApiKeyAction → End
3. ApiKeyAction 設定：動作=暫停、對象=指定 Key、挑一把 P2 E2E 測試 key
   （如 `ak_d939f99a9d4c1eb3`，勿動 `ik_5ad9de314382ac38`，那是遷移後的正式 OD key）
4. 送單觸發，等 executor 輪詢執行
5. 驗證：
   ```sql
   -- key 應變 suspended、suspended_reason 有值
   SELECT key_id, status, suspended_reason FROM api_keys WHERE key_id='ak_d939f99a9d4c1eb3';
   -- 節點執行記錄
   SELECT node_type, status, error_message FROM fw_node_execution_queue
   ORDER BY id DESC LIMIT 5;
   ```
6. 測完把 key resume 回來（`/security/api-keys/` UI 或 SQL）

自動化登入範例（curl）：
```bash
BASE=http://192.168.0.16:7000/beakplatform
curl -s -c cj.txt -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d '{"account":"admin-ethanyu@beluga.com","password":"ApiKeyTest2026"}'
# 之後帶 -b cj.txt 打 API；表單版登入有三欄位防機器人機制，不要用
```

### 2. 突發保護 B/C

規格：`docs/handoff_burst_protection_ABC.md`（A 已完成）。內容：executor 並發封頂、intake 事件聚合。

### 3. DevTools 9222 連通排查（用戶主導，見下節）

### 4. 下一版本週期的遺留清理（還沒到時間，勿現在做）

刪 `od_intake_keys` 表 + `/open-defense/intake-keys` 頁 + `intake_key_service.py`（規格 §7 P2 節有記）。

## DevTools（chrome-devtools-mcp）啟動與測試 SOP

完整部署程序在 **BeakBroodNest atom #4608**（那份才是權威，本節是速查）。
BeakDevF12 專案本身已廢棄（atom #4607），但 9222 CDP 鏈路是現行方案，沒有棄用。

架構：Windows(192.168.0.10) CDP Chrome listen 127.0.0.1:9222 → netsh portproxy 轉 LAN
→ Ubuntu 端 chrome-devtools-mcp `--browserUrl=http://192.168.0.10:9222`（user scope，已註冊）。

### 2026-07-08 03:20 現況（未解，明天排查）

用戶已用測試帳號啟動 Chrome，但 Ubuntu 端 `curl -m 5 http://192.168.0.10:9222/json/version`
**timeout**（不是 refused）。研判方向：

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

## 明天要討論的事（用戶指定）

**/upcom 交接品質改善**：用戶觀察到新對話開場常自己試誤猜很久（例：本 session 猜登入方式、
猜 API 前綴 `/api/workflows/` vs `/api/form-workflow/`）。提案：以後交接時趁當前對話記憶完整，
交接文件直接附上「可執行的範例程式 / 簡短 SOP」（登入 curl、驗證指令、關鍵路徑），
而不是只寫敘述。本檔的 E2E SOP 與 DevTools 速查就是照這個想法先做的樣板，明天討論後
決定是否納入 /upcom 固定格式。

## 本 session 順手修掉的既有 bug（已 commit，供追溯）

1. `wf-node-alert-broadcast.js` 角色/部門 fetch 前綴錯誤（404 被 catch 吃掉）→ `/api/workflows/data/`
2. `workflow_node_definitions.icon` 23 筆殘留舊前綴 `/bp/static/` 導致 palette 圖示全破圖
   → DB 正規化 + API 以 `request.script_root` 動態補前綴
3. node-definitions category_map 缺「安全」→ DecisionWriter/ApiKeyAction 掉進「基本節點」
   → 前後端補 `security`／「安全管控」分類
