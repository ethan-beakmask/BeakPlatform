# 流程節點測試盤點表

**目的**：公開本專案之前，每一種流程節點都要有被實際驗證過的紀錄。
本表是唯一的進度來源，**編號 `NT-xx` 是穩定識別碼**，可被其他文件、BBN 卡片、
commit message、待辦引用（例：「NT-13 已完成，見 `/opt/tmp/verify/20260830-end-cancel-mode.log`」）。

編號一經指派**不得重排、不得回收**。新增節點型別時往後接續編號。

## 狀態定義（不要自行擴充）

| 狀態 | 判準 |
|---|---|
| **端到端** | 真的經由 `beakplatform-dev-executor` spawn `node_runner` 執行過，且留有落地憑證 |
| **單元** | 有 pytest 覆蓋，但沒有經由 executor 實跑 |
| **未驗證** | 以上皆無。**「平常在用、看起來正常」不算驗證** |

**憑證缺席就是未驗證。** 「我測過了」若沒有落地輸出，事後與「我以為我測過了」無法區分
（見專案 CLAUDE.md 的 VERIFY-01）。憑證一律放 `/opt/tmp/verify/<日期>-<主題>.log`。

## 盤點表

節點型別取自 `workflow_node_definitions` 與 `node_handlers/factory.py` 的註冊清單，
2026-08-30 現況共 27 種（其中 2 種 `is_active=false`）。

| 編號 | node_type | 顯示名 | 分類 | 狀態 | 憑證 / 測試檔 |
|---|---|---|---|---|---|
| NT-01 | `Start` | 開始 | 基本 | 端到端 | `20260830-end-cancel-mode.log` |
| NT-02 | `End` | 結束 | 基本 | 端到端 | 三種 finish_mode 全數實測，見下方 §本次完成 |
| NT-03 | `ApiKeyAction` | API Key 處置 | 安全 | 未驗證 | — |
| NT-04 | `ApiKeyIssue` | API Key 核發 | 安全 | 未驗證 | — |
| NT-05 | `Branch` | 分支 | 控制 | 未驗證 | 行為已文件化（CLAUDE.md「流程 graph 的引擎行為」），但無落地憑證 |
| NT-06 | `Condition` | 條件判斷 | 控制 | 停用中 | `is_active=false`，未註冊 handler |
| NT-07 | `Converge` | 匯合 | 控制 | 未驗證 | — |
| NT-08 | `Delay` | 暫停 | 控制 | 端到端 | `20260830-end-cancel-mode.log`（30 秒等待、WAITING→PENDING 喚醒） |
| NT-09 | `ParallelFork` | 並行分支 | 控制 | 端到端 | `20260830-end-cancel-mode.log`（兩支同時推進） |
| NT-10 | `ParallelJoin` | 並行匯合 | 控制 | 未驗證 | 逾時出線（`timeout_edge_id`）尤其未驗 |
| NT-11 | `SubFlow` | 子流程 | 控制 | 端到端 | `20260830-end-cancel-mode.log`；**修復後才首次成功**，見 §缺陷 |
| NT-12 | `Switch` | 條件分支 | 控制 | 停用中 | `is_active=false`，未註冊 handler |
| NT-13 | `AiAgent` | AI 分析 | 整合 | 端到端 | 2026-08-20 經 executor 實跑（發現 `AI_NODE_CLI_PATH` 問題）；單元測試 `test_ai_agent_node.py` |
| NT-14 | `EmailRelay` | Email 轉發 | 整合 | 未驗證 | `require_system_admin=true` |
| NT-15 | `SqlExecutor` | SQL 執行 | 整合 | 端到端 | `20260830-end-cancel-mode.log`；單元測試 `test_sqlexecutor_node.py`（47 項） |
| NT-16 | `SubSystemProvision` | 子系統配置 | 整合 | 未驗證 | — |
| NT-17 | `Abandon` | 中止 | 系統 | 未驗證 | 與 NT-11 共用父流程喚醒邏輯，**同一個 `created_by` bug 的鄰居，要一併檢查** |
| NT-18 | `SysTelegram` | 系統 Telegram | 系統 | 未驗證 | `require_system_admin=true` |
| NT-19 | `FormAdapter` | 簽核 | 表單 | 未驗證 | 日常在用，但無落地憑證；授權判定點共 12 處（`task_authorizer.py`） |
| NT-20 | `OpFieldRead` | 讀取欄位 | 變數 | 未驗證 | — |
| NT-21 | `OpFieldWrite` | 寫入欄位 | 變數 | 未驗證 | — |
| NT-22 | `OpSet` | 設定變數 | 變數 | 未驗證 | — |
| NT-23 | `DecisionWriter` | 防禦決策 | 資安處置 | 部分 | 保護清單服務層有測試（`test_od_protected_targets.py`）；節點本身未經 executor 留證 |
| NT-24 | `AlertBroadcast` | 緊急廣播 | 通知 | 未驗證 | `broadcast_code` 不做變數替換，同 code 會覆蓋前一則 |
| NT-25 | `EmailAdapter` | Email 通知 | 通知 | 未驗證 | — |
| NT-26 | `NavbarBroadcast` | 跑馬燈廣播 | 通知 | 未驗證 | — |
| NT-27 | `Telegram` | Telegram 通知 | 通知 | 未驗證 | — |

進度：端到端 7 / 單元 0 / 部分 1 / 未驗證 17 / 停用 2。

**剩餘項目的待辦是 BBN `PF-172`**（`note_search("PF-172")` 取全文，含依風險排序的優先順序）。
`NT-06 Condition` 與 `NT-12 Switch` 是 `is_active=false` 且未註冊 handler，
**要先決定修好還是刪掉**，不要直接排進測試。

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
要連 DB 查詢一起斷，需在殺 process 前對該連線發 `pg_cancel_backend()`，
代價是 SqlExecutor 執行時要把 backend PID 記進 queue 記錄。**目前不做。**
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

本次的測試環境建置腳本與監控腳本已刪除（測試資料為拋棄式），但手法可重用：

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
