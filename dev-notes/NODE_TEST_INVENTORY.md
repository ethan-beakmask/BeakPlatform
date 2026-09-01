# 流程節點測試盤點表

**目的**：公開本專案之前，每一種流程節點都要有被實際驗證過的紀錄。
本表是唯一的進度來源。

## 編號規則

**`NT` = Node Test，一種流程節點型別配一個編號**，格式 `NT-<兩位數>`。
它是本表自訂的穩定識別碼，可被其他文件、BBN 卡片、commit message、待辦引用
（例：「NT-13 已完成，見 `/opt/tmp/verify/20260830-end-cancel-mode.log`」）。

- 編號一經指派**不得重排、不得回收**，新增節點型別時往後接續（下一個是 NT-30）
- 編號綁的是 **`node_type` 字串**，不是顯示名稱——改中文顯示名不換編號
- 與其他編號體系無關：`PF-xx` 是 BBN 待辦，`AUTH-01`／`TZ-01` 這類是 CLAUDE.md 的規範條號

## 狀態定義（不要自行擴充）

| 狀態 | 判準 |
|---|---|
| **端到端** | 真的經由 `beakplatform-dev-executor` spawn `node_runner` 執行過，且留有落地憑證 |
| **單元** | 有 pytest 覆蓋，但沒有經由 executor 實跑 |
| **未驗證** | 以上皆無。**「平常在用、看起來正常」不算驗證** |
| **已退役** | 定義已從工具列移除，但 handler 與 factory 註冊保留，既有流程／快照仍可執行 |
| **已刪除** | 定義、handler、前端面板全數移除，且模板與發行快照中皆無使用 |

**憑證缺席就是未驗證。** 「我測過了」若沒有落地輸出，事後與「我以為我測過了」無法區分
（見專案 CLAUDE.md 的 VERIFY-01）。憑證一律放 `/opt/tmp/verify/<日期>-<主題>.log`。

## 盤點表

節點型別取自 `workflow_node_definitions` 與 `node_handlers/factory.py` 的註冊清單，
2026-08-30 現況共 29 種（其中 4 種已刪除或退役）。

| 編號 | node_type | 顯示名 | 分類 | 狀態 | 憑證 / 測試檔 |
|---|---|---|---|---|---|
| NT-01 | `Start` | 開始 | 基本 | 端到端 | `20260830-end-cancel-mode.log` |
| NT-02 | `End` | 結束 | 基本 | 端到端 | 三種 finish_mode 全數實測，見下方 §本次完成 |
| NT-03 | `ApiKeyAction` | API Key 處置 | 安全 | 未驗證 | — |
| NT-04 | `ApiKeyIssue` | API Key 核發 | 安全 | 未驗證 | — |
| NT-05 | `Branch` | 分支 | 控制 | 未驗證 | 行為已文件化（CLAUDE.md「流程 graph 的引擎行為」），但無落地憑證 |
| NT-06 | `Condition` | 條件判斷 | 控制 | 已刪除 | 2026-08-30 刪除定義（migration 119），無 handler 檔 |
| NT-07 | `Converge` | 匯合 | 控制 | 已刪除 | 2026-08-30 刪除，功能與 NT-10 ParallelJoin 重疊且回 pending 後永不被喚醒 |
| NT-08 | `Delay` | 暫停 | 控制 | 端到端 | `20260830-end-cancel-mode.log`（30 秒等待、WAITING→PENDING 喚醒） |
| NT-09 | `ParallelFork` | 並行分支 | 控制 | 已退役 | 2026-08-30 移出工具列（無實際功能：不放此節點也會走所有出邊）。handler 與 factory 註冊保留，既有快照照跑 |
| NT-10 | `ParallelJoin` | 並行匯合 | 控制 | 端到端 | `20260830-paralleljoin-any-e2e.log`（ALL／ANY／`release_once` 三組，含 mutation 對照）。**逾時出線 `timeout_edge_id` 仍未驗** |
| NT-11 | `SubFlow` | 子流程 | 控制 | 端到端 | `20260830-end-cancel-mode.log`；**修復後才首次成功**，見 §缺陷 |
| NT-12 | `Switch` | 條件分支 | 控制 | 已刪除 | 2026-08-30 刪除，行為與 ParallelFork 一字不差 |
| NT-13 | `AiAgent` | AI 分析 | 整合 | 端到端 | 2026-08-20 經 executor 實跑（發現 `AI_NODE_CLI_PATH` 問題）；單元測試 `test_ai_agent_node.py` |
| NT-14 | `SysEmailRelay` | 系統 Email 轉發 | 系統 | 端到端 | 2026-08-31 PF-188 四層授權面實測（`20260831-pf188.log`）；2026-09-01 PF-193 實際寄信成功（`20260901-pf193-e2e.log`）：收件私人測試信箱（值見 `scripts/.secrets-scan-extra` 末行或 BBN #5353，不進版控）、主旨 `[BeakPlatform 測試] PF-193 端對端驗證 PROC-20260901-0001`。**Ethan 已確認收到（進了 Gmail 垃圾信匣）**——日後重跑要去垃圾信匣找，收不到不等於沒寄達 |
| NT-15 | `SqlExecutor` | SQL 執行 | 整合 | 端到端 | `20260830-end-cancel-mode.log`；單元測試 `test_sqlexecutor_node.py`（47 項） |
| NT-16 | `SubSystemProvision` | 子系統配置 | 整合 | 未驗證 | — |
| NT-17 | `Abandon` | 中止 | 系統 | 未驗證 | 與 NT-11 共用父流程喚醒邏輯，**同一個 `created_by` bug 的鄰居，要一併檢查** |
| NT-18 | `SysTelegram` | 系統 Telegram | 系統 | 端到端 | 2026-08-31 PF-188 授權面同 NT-14；2026-09-01 PF-193 實際發送成功（`20260901-pf193-e2e.log`）：測試頻道 `-4645997172`、`message_id=51561`、內容含 `PROC-20260901-0001` |
| NT-19 | `FormAdapter` | 簽核 | 表單 | 未驗證 | 日常在用，但無落地憑證；授權判定點共 12 處（`task_authorizer.py`） |
| NT-20 | `OpFieldRead` | 讀取欄位 | 變數 | 未驗證 | — |
| NT-21 | `OpFieldWrite` | 寫入欄位 | 變數 | 未驗證 | — |
| NT-22 | `OpSet` | 設定變數 | 變數 | 未驗證 | — |
| NT-23 | `DecisionWriter` | 防禦決策 | 資安處置 | 部分 | 保護清單服務層有測試（`test_od_protected_targets.py`）；節點本身未經 executor 留證 |
| NT-24 | `AlertBroadcast` | 緊急廣播 | 通知 | 未驗證 | `broadcast_code` 不做變數替換，同 code 會覆蓋前一則 |
| NT-25 | `EmailAdapter` | Email 通知 | 通知 | 未驗證 | — |
| NT-26 | `NavbarBroadcast` | 跑馬燈廣播 | 通知 | 未驗證 | — |
| NT-27 | `Telegram` | Telegram 通知 | 通知 | 未驗證 | — |
| NT-28 | `OsExecutor` | OS 命令 | 系統 | 端到端 | `20260830-osnode.log`（四分法四條路徑、兩道授權閘門、cancel 協同兩種、併發上限、引號化對照） |
| NT-29 | `OsFileRead` | 檔案讀取 | 系統 | 端到端 | `20260830-osnode.log`（四種模式、兩道授權閘門、symlink 與 `../` 逃逸各一次、regex／line_start／occurrence 三軸） |

進度：端到端 9 / 單元 0 / 部分 1 / 未驗證 15 / 已退役 1 / 已刪除 3。

**剩餘項目的待辦是 BBN `PF-172`**（`note_search("PF-172")` 取全文，含依風險排序的優先順序）。
`NT-06 Condition`、`NT-07 Converge`、`NT-12 Switch` 已刪除；`NT-09 ParallelFork`
已退役但保留 handler 與 factory 註冊供既有快照執行。

## 2026-08-30 第三批：主機側節點 NT-28 / NT-29（憑證 `/opt/tmp/verify/20260830-osnode.log`）

PF-181（OsExecutor）與 PF-182（OsFileRead）一併上線，規格見 `dev-notes/OS_EXECUTOR_SPEC.md`。
兩者的授權閘門刻意各自獨立（`OS_NODE_ENABLED` / `OS_FILE_READ_NODE_ENABLED` ＋
兩份企業白名單），驗收時分別關掉各自的開關實測過。

### NT-28 OsExecutor 實測矩陣

| 場景 | 結果 |
|---|---|
| `/bin/echo` | `_result=ok`、exit 0、stdout 進變數與落檔 |
| `/bin/false` | `_result=exception` / `_error_kind=exit_code`，queue **SUCCESS 不重試** |
| `sleep 3117 & sleep 3117`，timeout 3s | `_result=timeout` / `_killed=group_sigterm`，**背景子孫全數收乾淨**（`pgrep -x sleep` 對照） |
| `wait_for_result=false` | `_result=dispatched` + `_unit=bp-<queue_sc>`，journal 有 Started |
| `expect_pattern` 命中／不命中 | `ok` ／ `exception`+`expect_pattern` |
| `expect_json` 合法／不合法 | `ok` ／ `exception`+`expect_json` |
| 企業未取得 `OsExecutor` grant（`workflow_node_org_grants`） | `exception`+`not_authorized`（reason 明確） |
| `OS_NODE_ENABLED` 註解掉後重啟 executor | `exception`+`not_authorized` |
| 併發 4 個（上限 3） | 3 RUNNING + 1 WAITING，排隊者稍後自行完成 |
| 例外通知無收件人 | 只記 WARNING，不影響節點結果 |

**cancel 協同兩種都驗過**：

1. 等待型：`Start →〔OsExecutor(sleep 2911 & sleep 2911)〕／〔End(cancel)〕` 並行圖，
   End 觸發後兩個 sleep 全數消失、OsExecutor queue 標 CANCELLED
   → node_runner 的 SIGTERM handler 有效
2. dispatched：`cancel_scope=unit` 時 journal 顯示 unit 在 8 秒後被 `Stopping/Stopped`；
   `cancel_scope=detach` 時 unit 不受流程取消影響，10 秒後自己 `exit 3`，
   事後 `systemctl show` 仍查得到 `Result=exit-code / ExecMainStatus=3`

**引號化的對照組**（等價於規格要求的 mutation 驗證，且不必改程式碼）：
同一筆測資 `; touch /opt/tmp/verify/PWNED_20260830 ; #`

| 寫法 | 展開後的命令 | 檔案有沒有被建立 |
|---|---|---|
| `${v.payload}` | `/bin/echo '; touch ... ; #'` | **沒有**（注入被中和） |
| `${v.payload!raw}` | `/bin/echo ; touch ... ; #` | **有**（證明測資本身真的可執行） |

### NT-29 OsFileRead 實測矩陣

檔案 `/opt/tmp/frtest/sample.log`（2000 行、含中文、3 行 ERROR）。

| 場景 | 結果 |
|---|---|
| `mode=tail` lines=3 | 正確取到最後三行，中文未破碼（反向 block 讀 + 最後才 decode） |
| `mode=head` lines=2 | 正確 |
| `mode=around` keyword=ERROR occurrence=all | 3 個窗口以 `--` 分隔、`_match_count=3` |
| `match_mode=regex` `payload-(37\|1200)$` | 2 個窗口、`_match_count=2` |
| `occurrence=last` | 只留最後一個窗口，但 `_match_count=3`（全檔計數） |
| `occurrence=first` / `max_windows` 達標 | 提早停止並標 `_scan_truncated=true` |
| 壞掉的 regex `([unclosed` | `exception` + `_error_kind=bad_pattern` |
| symlink 逃逸（`evil.link -> /etc/passwd`） | `exception` + `path_denied` |
| `../../etc/passwd` | `exception` + `path_denied` |
| 企業未取得 `OsFileRead` grant（`workflow_node_org_grants`） | `exception` + `not_authorized` |
| `OS_FILE_READ_NODE_ENABLED` 註解掉後重啟 | `exception` + `not_authorized` |

### 本批修掉的三個缺陷（都是實測才發現的）

1. **executor 的 WAITING 喚醒清單漏了 OsExecutor**（`workflow_executor.py` 兩處）。
   併發上限回 `waiting` 的節點永遠不會被撿回來，實測第 4 個節點的 `scheduled_at`
   過期數分鐘仍停在 WAITING。加進清單後立刻被喚醒並完成
2. **OsFileRead `occurrence=first` / `max_windows` 達標時窗口重複輸出一次**：
   `break` 之前沒有清掉 `current`，迴圈後的收尾又 append 了同一個窗口
   （症狀是輸出重複同一段並多出一條 `--`）
3. **OsFileRead `tail` 的 `_truncated` 恆為 true**：原本用 `position > 0` 判定，
   而 tail 本來就只讀檔尾，於是這個旗標對 tail 失去鑑別力。
   改為「撞到 `MAX_READ_BYTES` 才算截斷」

### 設計器面板

`wf-node-os-executor.js` / `wf-node-os-file-read.js`，接線在 `wf-accordion.js`（清單 +
dispatch）、`wf-save.js`（case）、`wf-render.js`（node type 正規化）、
`workflow_designer.html`（script）。瀏覽器實測記錄在同一份憑證檔尾段：
顯示/隱藏切換、select 初次渲染值、collect 的型別轉換（exit codes / extra_env /
notify_to）全部逐項檢查過，console 無 error。

## 2026-08-30 第二批：節點整併（憑證 `/opt/tmp/verify/20260830-paralleljoin-any-e2e.log`）

**NT-10 ParallelJoin 的成功判準**（第 4 項要求，供後續覆核）：

| 設定 | 預期狀態轉移 | 預期 queue 筆數 |
|---|---|---|
| `join_mode=ALL` | 未到齊回 `waiting` + `scheduled_at` +10s，到齊才 SUCCESS 並推進 | PJ 1 筆、下游 1 筆 |
| `join_mode=ANY` | 第一條入線 SUCCESS 即放行 | PJ 2 筆、下游依 `release_once` 而定 |
| `release_once=true`（預設） | 第 2 筆 PJ 回 `skip_advance=true` / `skip_advance_reason=release_once` | 下游 **1 筆** |
| `release_once=false` | 第 2 筆 PJ 照常放行 | 下游 **2 筆** |

測試 graph 刻意不接 `End`：接了流程會 COMPLETED，executor 隨即取消未完成節點，
就觀察不到第二條入線抵達時的行為。這是測 ANY 模式時的必要條件。

**本批同時完成的整併**：Converge / Switch / Condition 刪除、ParallelFork 退役、
Branch fallback 修正（非 route 一律不推進出邊）、新增 `skip_advance` 旗標。
瀏覽器實測憑證 `/opt/tmp/verify/20260830-node-cleanup-after.log`。

## 本次完成（2026-08-30，憑證 `/opt/tmp/verify/20260830-end-cancel-mode.log`）

測試場景：主流程 `Start → ParallelFork →〔SubFlow → 子流程(SqlExecutor 45 秒查詢)〕／〔Delay 30s → End〕`，
真實經由 executor 執行，逐 3 秒取樣 OS 進程、PostgreSQL backend、DB 狀態三者。

| 編號 | 驗證內容 | 結果 |
|---|---|---|
| NT-02 | `End` finish_mode = `detach` | 正常。不處理其他節點，未啟動的節點由 executor 下輪撿到時取消 |
| NT-02 | `End` finish_mode = `strict` | 正常。偵測到未完成節點退回 WAITING、`scheduled_at` 推後 30 秒重試，等到子流程收完才結束（`has_failures=false`） |
| NT-02 | `End` finish_mode = `cancel` | **修復後**正常。整棵流程樹（含子流程）節點與 instance 同時 CANCELLED，OS 進程被中斷 |
| NT-01 | `Start` | 正常 |
| NT-08 | `Delay` | 正常。30 秒等待精確，`scheduled_at` 自行 commit 落地 |
| NT-09 | `ParallelFork` | 正常。兩支同時推進、互不干擾 |
| NT-11 | `SubFlow` | **修復後**正常。建立子流程實例、執行、回頭喚醒父流程 SubFlow 節點 |
| NT-15 | `SqlExecutor` | 正常。白名單重查、唯讀交易、`statement_timeout` 均生效 |

單元測試：`backend/tests/test_workflow_cancel_mode.py`（5 項，全部做過 mutation 驗證）。

## 本次修掉的缺陷

**一、`SubFlow` 從上線起 100% 失敗**（NT-11）
`subflow_handler.py` 建 `FwWorkflowInstance` 時傳了不存在的 `created_by='system'`，
`TypeError` → 重試 3 次 → FAILED。判別特徵：全庫 `fw_workflow_instances`
沒有任何 `workflow_depth > 0` 的記錄。

**二、`End` cancel 模式只做半套**（NT-02）
查詢範圍是單一 instance（子流程完全不在內），且對 RUNNING 節點只改 DB 欄位、
不碰 `process_id`。實測主流程 COMPLETED 後子流程又活了 75 秒。
被取消的節點跑完還會把自己蓋回 SUCCESS，事後看不出曾被取消。

## 已知邊界（不是缺陷，設計上的取捨）

**殺掉 node_runner 不會中斷它已經發動的外部作業。** 實測 SIGTERM 後
`pg_sleep(45)` 的 PostgreSQL backend 仍活到查詢自然結束——PostgreSQL 只有在
要寫回 socket 時才發現 client 斷線。同理適用於已送出的 HTTP 請求。
要連 DB 查詢一起斷，需在殺 process 前對該連線發 `pg_cancel_backend()`。
**Ethan 2026-08-30 定案不做**（BBN `PF-173` 已結案）：SqlExecutor 有
`statement_timeout`（上限 60 秒）兜底，多佔用連線幾秒到幾分鐘沒有實質影響，
且 PostgreSQL 本身另有連線與資源的維護機制，不需要由本專案補這一層。
**這不是延後，是決定不做——未來 session 不要重新把它當成待辦。**
（AiAgent 的 claude CLI 是子進程、在同一個 process group 內，會被一起收掉。）

## 端到端達標的最低要求（不滿足就只能記「未驗證」）

冷讀審核指出：只寫「放 `/opt/tmp/verify/`」會讓不同人留的憑證無法互相比較。
一筆憑證要能被別人覆核，log 內必須看得到這五項：

1. **測試 graph 的 JSON**（或產生它的腳本），含每個節點的 config
2. **`fw_workflow_instances.secure_code`** 與 `execution_code`（後續查詢的錨點）
3. **三者同步取樣**：OS 進程（`ps` grep node_runner）、外部資源（`pg_stat_activity` /
   收件匣 / API 對象）、DB 狀態（queue + instance）。**只有 DB 不算端到端**
4. **該節點的成功判準**：預期的狀態轉移、寫進哪張表哪個欄位、走哪條出邊。
   驗證前先寫下來，不要事後看到什麼就算什麼
5. **清理結果**（殘留查詢回 0）

新增單元測試時另外要做 **mutation 驗證**：把被測的行為改回壞掉的樣子，
確認測試會紅。恆真斷言讀起來像有保障，比沒測更危險。

**各節點的成功判準（第 4 項）在驗證該節點時補進本表對應列的「憑證」欄**，
不要另開文件。節點的 config key 一律看 handler class 的 docstring
（`modules/form_workflow/services/node_handlers/<型別>_handler.py`，
`sqlexecutor_handler.py` 與 `ai_agent_handler.py` 是寫得最完整的範例）——
`workflow_node_definitions.config_schema` **沒有任何消費者，不能當權威**。

## 環境操作（每次驗證都會用到）

```bash
# 改 handler / workflow_engine.py 後必做（executor 是獨立進程，不重啟等於沒改）
sudo systemctl restart beakplatform-dev-executor.service
systemctl is-active beakplatform-dev-executor.service        # 要回 active

# 確認 executor 真的在撿 queue（restart 後跑一個測試流程，看有沒有這行）
sudo journalctl -u beakplatform-dev-executor.service --since "-2 min" | grep "啟動節點"
```

只改 handler **不需要**重啟 web 服務（`beakplatform-dev.service`）——
node_runner 是每次執行都重新 spawn 的獨立進程。改了模板或 web 路由才要重啟 web。

測試企業一律用 **BELUGA `_9c8TewkRkCBEf3XsUdqeF`**（本次測試用的，資料齊全）。

## 怎麼補測（可直接複製使用）

**現成工具：`dev-notes/tools/node_probe.py`**（2026-08-30 PF-181/182 驗收時寫的，
NT-28 / NT-29 的整份實測矩陣都是用它跑出來的）。它建 template + instance +
一筆 Start 的 PENDING queue 記錄，executor 自己會撿起來跑完整流程：

```bash
set -a && source .env && set +a
# 線性圖 Start -> <節點> -> End(cancel)
PROBE_NODE_TYPE=OsExecutor venv/bin/python dev-notes/tools/node_probe.py \
    create ok '{"command":"/bin/echo hi","result_var":"r","timeout_seconds":30}'
# 並行圖 Start ->〔受測節點〕/〔End(cancel)〕，驗 cancel 協同用
PROBE_NODE_TYPE=OsExecutor venv/bin/python dev-notes/tools/node_probe.py \
    create cancel-test '<config json>' parallel
# 建立時順便寫流程變數（驗變數插值用）
... create quote '<config json>' 'var:payload=; touch /tmp/PWNED ; #'

venv/bin/python dev-notes/tools/node_probe.py wait <instance_sc> 120
venv/bin/python dev-notes/tools/node_probe.py show <instance_sc>   # queue／變數／log 三者
```

清理（測完一定要做，否則測試模板會出現在流程列表上）：

```sql
BEGIN;
CREATE TEMP TABLE probe_inst AS
  SELECT id, secure_code FROM fw_workflow_instances WHERE execution_code LIKE 'OSPROBE-%';
DELETE FROM fw_node_execution_logs  WHERE workflow_instance_id IN (SELECT id FROM probe_inst);
DELETE FROM fw_node_execution_queue WHERE workflow_instance_secure_code IN (SELECT secure_code FROM probe_inst);
DELETE FROM fw_workflow_variables   WHERE workflow_instance_secure_code IN (SELECT secure_code FROM probe_inst);
DELETE FROM fw_workflow_instances   WHERE id IN (SELECT id FROM probe_inst);
DELETE FROM fw_workflow_templates   WHERE code LIKE 'OSPROBE\_%';
COMMIT;
```

以下是更早期（End cancel 那批）的手法，涉及 SqlExecutor 的臨時 SP，仍可參考：

```bash
# 1. 造一個會佔住 subprocess 的節點：註冊臨時 SP 給 SqlExecutor 用
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev <<'SQL'
CREATE OR REPLACE FUNCTION fw_sp.test_sleep(p_org_secure_code text, p_seconds integer)
RETURNS TABLE(slept integer) LANGUAGE plpgsql AS $$
BEGIN PERFORM pg_sleep(p_seconds); RETURN QUERY SELECT p_seconds; END; $$;
INSERT INTO fw_sql_procedures
  (secure_code, org_secure_code, code, function_name, display_name, description,
   parameters, result_mode, result_columns, max_rows, is_active, is_deleted)
VALUES ('testsleepproc0000000000000000001', NULL, 'test_sleep', 'test_sleep',
   '測試用延遲查詢', '測完刪除',
   '[{"name":"p_org_secure_code","type":"text"},{"name":"p_seconds","type":"integer","required":true}]'::jsonb,
   'rows', '[]'::jsonb, 10, true, false);
SQL

# 2. 不必經表單提交：直接建 FwWorkflowInstance（status=RUNNING + graph_snapshot）
#    與一筆 node_type='Start' 的 PENDING queue 記錄，executor 會自己撿起來跑
#    （FwWorkflowInstance 與 FwNodeExecutionQueue 都沒有 created_by 欄位，傳了會 TypeError）

# 3. 監控三者同步取樣（缺任一項都會誤判）
ps -eo pid,etimes,args --no-headers | grep 'form_workflow.services.node_runner' | grep -v 'bash -c'
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -c \
  "SELECT pid, state, left(query,40) FROM pg_stat_activity WHERE query LIKE '%test_sleep%' AND pid<>pg_backend_pid();"
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -F'|' -c \
  "SELECT wi.workflow_depth, q.node_id, q.status, q.process_id
   FROM fw_node_execution_queue q JOIN fw_workflow_instances wi
     ON wi.secure_code=q.workflow_instance_secure_code
   WHERE wi.secure_code='<root>' OR wi.root_instance_code='<root>'
   ORDER BY wi.workflow_depth, q.id;"

# 4. 清理（順序固定，少一張表會被 FK 擋下）
#    fw_node_execution_logs -> fw_workflow_variables -> fw_node_execution_queue
#    -> fw_workflow_instances -> fw_workflow_templates -> fw_sql_procedures -> DROP FUNCTION
```

**三個一定要知道的**：

- **node_runner 的 stdout/stderr 全進 `DEVNULL`**（`workflow_executor.py`），
  所以節點執行細節**不在 journal 裡**，只能靠 DB 狀態反推。
  這是 cancel 缺口長期沒被發現的直接原因
- 改 handler 或 `workflow_engine.py` 後**必須重啟 `beakplatform-dev-executor`**（獨立進程）
- 端到端驗證**不能只看 DB**：DB 顯示 CANCELLED 而進程仍在跑，正是修復前的實況

---

## 附：節點執行與 End 三模式（2026-08-30 從 CLAUDE.md 移入）

> 「重啟 executor 會殺掉執行中節點」那條仍留在 `CLAUDE.md` 的「服務啟動」，
> 因為它會靜默卡死流程。

**每個節點 = 一個獨立 OS subprocess**（`node_runner`，`start_new_session=True` 所以 pgid == pid），
PID 記在 `fw_node_execution_queue.process_id`。動這塊之前先看盤點表，
它記著每種節點的驗證狀態與編號 `NT-xx`（可被其他文件引用）。

四件猜不到的：

- **node_runner 的 stdout/stderr 全進 `DEVNULL`**，節點執行細節**不在 journal 裡**，
  只能靠 DB 狀態反推。這是 End cancel 缺口長期沒被發現的直接原因
- **父子流程的關聯在 `fw_workflow_instances`，不在 queue 表**：
  `root_instance_code`（主流程自己是 NULL，子孫鏈式繼承同一個根）。
  queue 表的 `calling_instance_code` / `parent_node_id` **只有子流程的 Start 節點有值**，
  拿它找子流程的中間節點一律漏掉。整棵樹的正確查法是
  `WHERE wi.secure_code = :root OR wi.root_instance_code = :root`（root 用 `root_instance_code or secure_code`）
- **`FwWorkflowInstance` 與 `FwNodeExecutionQueue` 都沒有 `created_by` 欄位**，
  傳了直接 `TypeError`。`subflow_handler` 就因此讓子流程從上線起 100% 失敗到 2026-08-30
- **殺 node_runner 不會中斷它已發動的外部作業**：SIGTERM 之後 `pg_sleep` 的
  PostgreSQL backend 仍活到查詢自然結束（要一起斷得發 `pg_cancel_backend()`，目前不做）。
  子進程（AiAgent 的 claude CLI）因為在同一個 process group 內，會被一起收掉

End 三模式的語意（`finish_mode`，預設 `detach`）：

| 模式 | 行為 |
|---|---|
| `detach` | 直接結束，其他節點不管，未啟動的由 executor 下輪撿到時取消 |
| `cancel` | **整棵樹**（含多層子流程）的節點與 instance 標 CANCELLED ＋ 對 RUNNING 節點送 SIGTERM/SIGKILL |
| `strict` | 等同 instance 內所有節點完成才結束；子流程靠 SubFlow 節點的 WAITING 間接等到 |

`cancel` 的唯一實作是 `WorkflowEngine.cancel_pending_nodes()`（另兩個呼叫端是管理員強制結案與
portal 撤單，行為一致）。**送訊號前一律先 `/proc/<pid>/cmdline` 比對 `--queue-item-code`**
（PID 會被重用，fail-closed 寧可不殺）、**且只在 pgid == pid 時才 killpg**
（否則會連帶殺掉 executor 整個 process group）。被取消的節點跑完不得把自己寫回 SUCCESS，
防護在 `node_runner.update_result()` / `handle_error()` / `advance_to_next_nodes()` 三處。

**`systemctl restart beakplatform-dev-executor` 會殺掉當下所有正在跑的節點進程**
（2026-08-30 實測）：unit 是 `KillMode=control-group` / `Delegate=no`，而
`start_new_session=True` **只脫離 process group 與 session，不脫離 cgroup**，
所以 node_runner 與它的子孫都在 executor 的 cgroup 內、一起被收掉。
而全 repo **沒有 stale RUNNING 的回收機制**，被這樣殺掉的節點會**永遠卡在 RUNNING**
（`_poll_and_execute` 只撿 PENDING 與少數 WAITING），流程就此靜止且不報錯。

所以「改 handler 後要重啟 executor」有代價：**重啟前先確認沒有流程在跑**
（`SELECT node_type, node_id, started_at FROM fw_node_execution_queue WHERE status='RUNNING';`），
事後發現卡住的只能手動改回 PENDING 或標 FAILED。要讓外部作業活過重啟，
唯一辦法是另建 systemd unit（`systemd-run`）把它移出 executor 的 cgroup ——
脈絡見 `dev-notes/OS_EXECUTOR_SPEC.md` 第七節與知識庫 #5316。

---

## 附：子流程的結束語意——End 三模式與 Abandon 對「上一層」與「整棵樹」的影響

> **【已過時，PF-200 於 2026-08-31 晚全面改掉】** 本節記的是改版前的現況，僅供考古。
> 現行行為：Abandon 已刪除；`End(cancel)`＝中止（記 CANCELLED），放在子流程時只收
> 「自己＋所有下層」（`scope='subtree'`），上一層被喚醒並依 `resultRouting` 分流；
> 三模式在子流程都有效；喚醒失敗改標父節點 FAILED。
> 定版規格見 `dev-notes/handoff_end_subflow_cancel_20260831.md` 第十節，
> 測試見 `backend/tests/test_end_node_semantics.py`。
>
> 2026-08-31 冷讀查證（PF-189-2 衍生）。上一節的 End 三模式表講的是**主流程**，
> 本節講的是**子流程裡的 End**——兩者行為完全不同，不要互相套用。

### 名詞：三個範圍不要混用

| 詞 | 欄位 | 意思 |
|---|---|---|
| **上一層** | `fw_workflow_instances.parent_instance_code` | 直接呼叫我的那一層。喚醒／推進走這個 |
| **整棵樹** | `root_instance_code`（root 自己是 NULL） | root ＋ 它的所有後代。`cancel_pending_nodes()` 走這個 |
| **root（主流程）** | `parent_instance_code IS NULL` 的那一個 | 唯一持有 `form_instance` 狀態的一層 |

多層時（孫 → 子 → 主）「上一層」是子、「整棵樹」含主，**兩者不是同義詞**。

### 分流點：子流程裡的 End，`finish_mode` 根本不會被讀

`end_handler.py::handle()` 第 49 行：

```python
if workflow_instance and workflow_instance.parent_instance_code:
    return self._handle_subflow_end(workflow_instance)   # ← finish_mode 在這條路上完全沒被讀
return self._handle_main_flow_end()                       # ← 只有這條讀 finish_mode
```

`_handle_subflow_end()` 回傳的 `data.finish_mode` 被**硬寫成 `'subflow_end'`**
（`_subflow_complete_result()`），所以 `node_runner` 的 `if finish_mode == 'cancel'`
永遠不成立。

**結論：子流程裡的 End，`detach` / `cancel` / `strict` 三種模式行為完全相同。**
唯一殘留的差別是 `wait_seconds` 的預設值（主流程 3 秒、子流程 1 秒），與模式無關。

在子流程的 End 面板上選 `cancel` 或 `strict` **不會報錯、不會有任何效果**，
這是本節最容易誤判的一點——設計者以為選了「取消/終止」就會收掉整棵樹，實際上不會。
要收掉整棵樹只有 Abandon。

### 六種組合的實際影響

| 放在哪 | 節點 | 上一層 | 整棵樹 | `fw_workflow_instances` | `fw_form_instances` |
|---|---|---|---|---|---|
| 主流程 | `End(detach)` | — | 不動，未啟動節點由 executor 下輪撿到才取消 | 自己 `COMPLETED` | **`APPROVED`** |
| 主流程 | `End(cancel)` | — | **全部節點與 instance 標 `CANCELLED`** ＋ RUNNING 送 SIGTERM | 自己 `COMPLETED` | **`APPROVED`** |
| 主流程 | `End(strict)` | — | 等同 instance 內節點完成才結束；有 FAILED 則 `has_failures` | 自己 `COMPLETED`（有失敗才 `FAILED`） | `APPROVED`（`FAILED` 時 `ERROR`） |
| 主流程 | `Abandon` | — | 同 `End(cancel)` | 自己 **`CANCELLED`** | **`CANCELLED`** |
| **子流程** | `End(任一模式)` | SubFlow 節點標 **SUCCESS**（`data` 無 `abandoned`）→ `advance_workflow()` 推進上一層 | **不受影響**，其他分支繼續跑 | 自己 `COMPLETED`，其他層不動 | **完全不動**（`complete_workflow()` 對子流程提前 return） |
| **子流程** | `Abandon` | 先做與 End 相同的「標 SUCCESS（`data.abandoned=True`）＋推進」 | **隨即整棵樹全部 `CANCELLED`**，含剛推進出來的那些節點 | 自己 `CANCELLED`，樹上其他 `PENDING`/`RUNNING` 的也被設 `CANCELLED` | **完全不動** ← 見下方缺口一 |

### 三個猜不到的後果

**一、子流程 Abandon 的「喚醒並推進上一層」是白做工。**
`_handle_subflow_abandon()` 先呼叫 `_complete_parent_subflow_node()` ＋
`_trigger_parent_next_nodes()` 把上一層推進出新節點，**然後**才 return
`finish_mode='cancel'`；`node_runner` 收到後呼叫
`cancel_pending_nodes(子流程 sc)`，而該函式的範圍是**整棵樹**——
剛建出來的那些 PENDING 節點當場被取消。

淨效果 ＝ 子流程 Abandon 收掉整棵樹（含主流程）。這與 `End(cancel)` 放在主流程的效果相同，
差別只在終態記成 `CANCELLED` 而不是 `COMPLETED`。

**二、【缺口】子流程 Abandon 之後，表單狀態停在 `PROCESSING` 永遠不會變。**
`complete_workflow()` 開頭就判斷「有 `parent_instance_code` → 跳過 form_instance 更新並 return」，
而收掉整棵樹的 `cancel_pending_nodes()` **完全不碰 `fw_form_instances`**
（只改 `fw_workflow_instances.status`）。

所以會出現：**流程樹全部 `CANCELLED`，但表單中心顯示「處理中」，且不會再有任何東西去更新它。**
主流程放 Abandon 沒有這個問題（走的是 `_handle_main_flow_abandon` → root 自己
→ `complete_workflow` 正常更新成 `CANCELLED`）。

這是本次冷讀新發現的，比 PF-189-2 原本記的「`abandoned` 標記讀不到」嚴重一級——
前者只是父流程分不出原因，後者是**案件狀態永久錯誤**，而且會被 SQL Sync 之外的
所有清單、統計、SLA 當成進行中的案子。

**三、【缺口】子流程 End 的失敗路徑會讓上一層永久卡死，Abandon 則不會。**
兩支 handler 都有同樣的兩個吞錯誤路徑（找不到 `parent_node_id`、喚醒時拋例外），
但後果完全不同：

- `Abandon`：吞掉之後仍回 `finish_mode='cancel'` → `cancel_pending_nodes` 收掉整棵樹，
  上一層那個 WAITING 的 SubFlow 節點跟著被 `CANCELLED`。**不會卡住**
- `End`：回的是 `'subflow_end'`，**不觸發 cancel**。上一層的 SubFlow 節點停在 `WAITING`，
  而 `workflow_executor` 只撿 `['Delay', 'End', 'ParallelJoin', 'OsExecutor']` 型別的 WAITING
  （兩處清單，`SubFlow` 不在內），全 repo 也沒有 stale WAITING 的回收機制。
  → **上一層永久卡死，不報錯、不逾時、無回收路徑**

`end_handler.py:116` 的警告文字「父流程可能卡住」其實是「一定卡住」。
PF-189 第 3 項原本只記了 `abandon_handler` 的吞錯誤路徑，**真正該優先修的是 `end_handler` 這一條**。

### `abandoned: True` 標記的實際去向（PF-189-2 的證據）

`abandon_handler._complete_parent_subflow_node()` 把它寫進上一層那筆 SubFlow queue item 的
`result` JSONB：

```python
parent_queue_item.success({
    'status': 'success', 'message': '子流程已中止',
    'data': {'child_instance_code': ..., 'abandoned': True, ...}
})
```

`fw_node_execution_queue.result` **沒有任何變數前綴讀得到**
（`f. / fi. / v. / wi. / n. / t.` 六種全部核對過）。而且承上「後果一」，
上一層被推進出來的節點隨即全被取消，所以**即使讀得到也沒有節點還活著能去讀它**。

也就是說 PF-189-2 想達成的「父流程用 Branch 分辨子流程是中止還是正常結束」，
在現行語意下**根本不可能**——不是缺一個變數，是 Abandon 的語意就是「整棵樹一起結束」。
要做到那件事得先決定：子流程 Abandon 應該只結束子流程（改成不觸發整棵樹 cancel），
還是維持現狀。**這是規格問題，不是實作問題。**

### 尚未實測、需要補的兩項

1. 子流程 Abandon 之後 `fw_form_instances.status` 的實際值（推導是停在 `PROCESSING`）
2. 子流程 End 走「找不到 `parent_node_id`」時上一層是否真的永久 WAITING（推導是會）

兩項都可用本檔「怎麼補測」那節的手法造流程樹驗證，不必經表單提交。

---

## 附錄：系統級通知節點（NT-14 / NT-18）的端對端驗證 runbook

2026-08-31 PF-188 只驗到授權面，端對端待辦是 **PF-193**。
本節是那張單的執行前提，寫在這裡是因為「節點 config 欄位名」「成功判準」
每次驗都會用到，不該只存在一次性的待辦裡。
（冷讀審核指出的缺口，2026-08-31 補。）

### 現成材料（系統預設企業，PF-188 建立）

| 用途 | 識別碼 |
|---|---|
| 流程模板「系統級節點驗收流程」 | `nAOBJWuKBa969StsPwv5OA` |
| 它的配對（publish 用） | `oCQwRov2rMIS1jbSFeg9Yg` |
| Telegram 設定組 | `c9WeYKveCBWxbn0t8kl6yn`「系統TG」／頻道名 `測試頻道`／chat_id `-4645997172` |
| quick-login 系統預設企業 ORG_ADMIN | `UC1oK01uDeKbG2MDwBflGD` |

**該模板目前只有 2 個節點（等同空白），要自己把節點接進去。**
`SysTelegram` / `SysEmailRelay` 是 `org_restricted`，只有系統預設企業看得到。

### 節點 config 欄位（2026-08-31 由設計器面板實測取得，不必再猜）

`SysTelegram`（handler 是 `telegram_handler.TelegramHandler`，與一般 `Telegram` 共用）：

```json
{"config_id": "<TelegramConfig secure_code>", "channel_name": "測試頻道",
 "message": "內容，支援 ${f.} ${v.} 變數", "parse_mode": "HTML",
 "disable_notification": false, "disable_web_page_preview": false}
```

`SysEmailRelay`（handler 是 `sys_emailrelay_handler.SysEmailRelayHandler`）：

```json
{"recipient_type": "manual",            // 或 "group"（小寫，大寫無效）
 "recipient_manual": "a@b.c, d@e.f",    // recipient_type=manual 時用
 "recipient_groups": ["<RecipientGroup secure_code>"],  // =group 時用
 "cc_manual": "", "subject": "主旨", "body": "內文",
 "body_type": "plain",                  // 或 "html"
 "priority": "normal"}                  // high / normal / low -> X-Priority 1/3/5
```

設定組與收件人群組的解析都限縮在**自己企業 or 系統企業**（PF-188），
填別家企業的 secure_code 會得到「找不到 Telegram 設定」而不是「無權使用」（刻意不洩漏存在與否）。

### 外部服務現況（本機環境事實）

```
systemctl is-active emailrelay              -> active
systemctl is-active beakplatform-dev-executor -> active   # 沒跑的話節點不會被執行
```

E-MailRelay 路徑由 `app.services.emailrelay_config.get_paths()` 決定，本機是：
`install_dir=/opt/emailrelay`（**小寫**，本節初版寫 `/opt/E-MailRelay` 是錯的，
2026-09-01 實測更正）、`submit_bin=/opt/emailrelay/sbin/emailrelay-submit`、
`spool_dir=/opt/emailrelay/spool`、`log_dir=/opt/emailrelay/logs`。

### 成功判準（三層都要看，只看一層會誤判）

| 層 | 怎麼看 | 注意 |
|---|---|---|
| 節點執行 | `fw_node_execution_logs`（level / message / node_type） | **不要只看 `fw_node_execution_queue.status`**，通知節點失敗時 queue 未必是 FAILED |
| 送出動作 | Telegram：log 內 `message_id`；SysEmailRelay：`ls -lt /opt/E-MailRelay/spool` 出現新檔 | spool 檔被 daemon 取走後會消失，要即時看 |
| 真的抵達 | Telegram 測試頻道實際出現訊息；收件匣實際收到信 | 訊息內容帶執行時間與 `execution_code`，才分得出不是舊訊息 |

**先確認沒有 RUNNING 節點再重啟 executor**（重啟會殺掉正在跑的節點且永遠卡在 RUNNING）：

```sql
SELECT node_type, node_id, started_at FROM fw_node_execution_queue WHERE status='RUNNING';
```

### 端對端已於 2026-09-01（PF-193）驗過，重跑時直接沿用這些事實

- 測試收件信箱（Ethan 指定的私人信箱，**明文不進版控**——值在 `scripts/.secrets-scan-extra` 末行（gitignored）或 BBN #5353）。**信會進 Gmail 垃圾信匣**
  （2026-09-01 Ethan 確認）——寄件來源無 SPF/DKIM 對齊是預期現象，
  驗收時去垃圾信匣找，別誤判成沒寄達
- **送件會被「您沒有填寫此表單的權限」擋下**：填寫權限走 `FwMappingPermission`
  （`fill_permission_service.py`），無記錄時預設要有 `EMPLOYEE` 角色，系統企業
  ORG_ADMIN 沒有。已補一筆 user 型授權（`created_by_name='PF193-TEST'`，
  grant_target 即該管理員），**留著沒刪**，之後重跑不會再撞到
- log 表欄位是 `log_level` / `log_message` / `log_data`（不是 level/message/data）；
  Telegram 成功的憑證是 `log_data` 裡的 `message_id`
- spool 檔被 daemon 取走後會消失；**取走＝遠端 SMTP 已收**（失敗會留 `.bad` 檔），
  搭配 `logs/emailrelay-YYYYMMDD.log` 的 `smtp connection to ...` 時間戳即可判定
- 驗完的清理：還原模板 graph（PUT 回備份）、發行快照**用 archive**
  （被使用過的版本 DELETE 會回 400「此版本已被使用過」）、實例軟刪除
- 2026-09-01 實測記錄：`20260901-pf193-e2e.log`，execution_code
  `PROC-20260901-0001`，Telegram `message_id=51561`（03:04）、
  郵件 03:05 交付 Google SMTP
