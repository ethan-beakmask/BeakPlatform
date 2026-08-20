# SqlExecutor 節點規格與安全設計（2026-08-20 第一版）

流程節點型別 `SqlExecutor`：讓流程呼叫**平台主庫裡事先登錄過**的 stored procedure，
把結果寫進流程變數，可再插一筆簽核註記給人類參考。
典型場景：請料單在核可前先查庫存夠不夠，不夠就在簽核意見提醒。

| 檔案 | 角色 |
|---|---|
| `modules/form_workflow/services/node_handlers/sqlexecutor_handler.py` | handler（安全核心，檔頭有完整設計說明） |
| `modules/form_workflow/models/sql_procedure.py` | 白名單 model `FwSqlProcedure` |
| `scripts/migrations/106_sqlexecutor_whitelist.sql` | schema `fw_sp`、白名單表、範例 SP 與範例資料 |
| `modules/form_workflow/api/workflows.py::get_sql_procedures` | 設計器下拉用的清單 API |
| `modules/form_workflow/static/.../js/wf-node-sql-executor.js` | 屬性面板 |
| `backend/tests/test_sqlexecutor_node.py` | 47 個測試（含四道防線的 mutation 驗證） |

## 七道防線（每一道都假設 config 是攻擊者可控的）

節點設定存在 `fw_workflow_templates.graph`（JSON），而 graph 可以透過 API 直接
PUT 改寫 —— **設計器的下拉選單不是防線**。

| # | 防線 | 實作位置 | 拔掉會怎樣 |
|---|---|---|---|
| 1 | schema 寫死 `fw_sp` | `ALLOWED_SCHEMA` 常數 | 可呼叫 `pg_catalog` 任何函式（讀檔、執行指令） |
| 2 | 執行期重查白名單 | `_load_procedure()` | 白名單等於不存在 |
| 3 | 識別碼正則 + `pg_proc` 覆核（含拒絕 SECURITY DEFINER） | `_verify_function()` | 提權、呼叫到不存在的多載 |
| 4 | org 由系統帶入，config 指定即整次拒絕 | `_build_params()` | 看得到別家企業的資料 |
| 5 | 參數一律 bind、型別依宣告轉換 | `coerce_param()` | SQL injection |
| 6 | 獨立連線 + `SET TRANSACTION READ ONLY` + `statement_timeout` | `_execute()` | 節點可以寫入／可以卡住整個 executor |
| 7 | 列數／單格長度／總長度三層截斷 | `normalize_rows()` | 一支 `SELECT *` 把整張表灌進流程變數 |

### 為什麼 org 過濾不能靠 RLS

平台主庫只有 10 張表開了 RLS，而且**都不是 FORCE**，`beakplatform` 又是表的 owner
—— owner 預設不受自己的 RLS policy 限制。所以**租戶邊界就在 SP 的 `WHERE` 裡**，
登錄新 SP 時這是唯一要人工確認的事。

### 為什麼 v1 只支援唯讀

寫入型 SP 會帶出一個必須先回答的問題：它與節點執行是否同一個交易？

- 同交易：SP 內不能 `COMMIT`（PostgreSQL function 的限制）
- 獨立交易：流程節點失敗時副作用留在資料庫裡 ——「流程回滾了但 SP 已經改了資料」

這個問題定案之前不開放。`_execute()` 一律 `SET TRANSACTION READ ONLY`，
由資料庫層保證，不是靠 handler 自律。**要放寬必須連同交易語意一起設計，
不是把那一行拿掉。**

## 白名單維護（刻意不做 Web UI）

**登錄一筆 ＝ 授權流程設計者呼叫那支 SP，屬於部署期決定**，所以走 migration。
新增一支 SP 的完整步驟：

```sql
-- 1) 函式建在 fw_sp，第一個參數固定 p_org_secure_code，且必須是實際 filter 條件
CREATE OR REPLACE FUNCTION fw_sp.my_query(p_org_secure_code TEXT, p_x TEXT)
RETURNS TABLE (col_a VARCHAR, col_b NUMERIC)
LANGUAGE sql STABLE SECURITY INVOKER   -- 不可以是 SECURITY DEFINER
AS $$
    SELECT t.col_a, t.col_b FROM public.some_table t
    WHERE t.org_secure_code = p_org_secure_code   -- 租戶邊界
      AND t.x = p_x;
$$;

-- 2) 登錄白名單（org_secure_code 留 NULL = 全平台共用）
INSERT INTO fw_sql_procedures
    (secure_code, org_secure_code, code, function_name, display_name, description,
     parameters, result_mode, result_columns, max_rows)
VALUES (generate_secure_code(), NULL, 'my_query', 'my_query', '我的查詢', '說明',
        '[{"name":"p_org_secure_code","type":"text","label":"企業識別碼","required":true},
          {"name":"p_x","type":"text","label":"條件","required":true}]'::jsonb,
        'rows', '[{"name":"col_a","label":"A"}]'::jsonb, 50);
```

三件必須對上，否則 handler 會拒絕（而且是**執行時**才拒絕，設計器存得下去）：

1. `parameters` 的第一筆必須是 `p_org_secure_code`
2. `parameters` 的筆數必須等於函式的參數個數（`pg_proc.pronargs`）
3. 函式名必須符合 `^[a-z][a-z0-9_]{0,62}$` 且該名稱在 `fw_sp` 內**只有一個多載**

`type` 只認 `text` / `integer` / `numeric` / `boolean` / `date`；
`result_mode` 只認 `scalar` / `row` / `rows`。

## 節點 config

```json
{
  "procedure_code": "check_stock",
  "params": {"p_item_code": "${f.item_code}"},
  "result_var": "stock",
  "timeout_seconds": 10,
  "write_approval_note": true,
  "note_template": "庫存查詢：${v.stock_item_name} 現有 ${v.stock_qty_on_hand}",
  "on_error": "error"
}
```

`params` 的值可用流程變數（`${f.欄位}` / `${v.變數}`），替換是**單次非遞迴**
（`base.py` 用 `re.sub` + callback），代入的內容不會被二次掃描。

## 寫出去的流程變數

| result_mode | 變數 |
|---|---|
| `scalar` | `<result_var>` = 單值 |
| `row` | `<result_var>` = dict，另外每個欄位一個 `<result_var>_<欄位名>` |
| `rows` | `<result_var>` = list[dict] |
| 三者皆有 | `<result_var>_count`、`<result_var>_found`、`<result_var>_truncated` |
| 失敗時 | `<result_var>_found`=False、`<result_var>_count`=0、`<result_var>_error` |

**`${v.x.y}` 這種巢狀取值流程引擎不支援**（`get_all_vars()` 是扁平 dict），
所以 `row` 模式才會另外攤平成 `<result_var>_<欄位名>` —— Branch 條件要比大小
就用攤平後的那個，或直接用 `scalar` 模式的 SP。

失敗時仍寫 `_found` / `_count`，是為了讓後續節點看得出這次沒有資料，
而不是拿到上一輪的舊值。

## 簽核註記

與 AiAgent 節點共用同一個出口 `fw_approval_records`：
`approver_secure_code=NULL`、`action='sql_note'`、`approver_name='SYSTEM'`。

有效簽核的判定用的是**白名單** `action.in_(['approved','rejected'])`
（`api/fc_pending.py:413`、`api/fc_batch.py:94`），所以 `sql_note` 天生不會被算進去。
註記內容寫入前一律 HTML 跳脫（`sanitize_for_comment`）。
**查詢失敗時只寫固定訊息**，DB 錯誤原文只進流程 log —— 錯誤訊息會洩漏 schema。

## 範例資料（開發機現況）

`fw_demo_inventory` 是示範用庫存表，兩家企業刻意放同一個料號 `A-1001`：
beluga 1200 / lion 5。用它驗跨企業隔離最直接。

| code | 模式 | 說明 |
|---|---|---|
| `check_stock` | row | 依料號查庫存與安全存量 |
| `low_stock_items` | rows | 列出低於安全存量的料號 |
| `stock_qty` | scalar | 單一料號的庫存量（給 Branch 比大小） |

## 已知限制與後續

- **只支援唯讀**（見上）
- **白名單沒有管理 UI**，新增走 migration
- `fw_sp` 內的函式若有同名多載，handler 會拒絕執行（無法判定要呼叫哪一個）
- 尚未在真實流程中跑過完整一輪（拖節點 → 發行 → 送單）；
  已驗到 `handle()` 全流程（含變數寫入與簽核註記），見
  `/opt/tmp/verify/20260820-sqlexecutor.log`

## 驗收紀錄

- 單元／整合測試：47 passed（`bash scripts/run_tests.sh tests/test_sqlexecutor_node.py -q`）
- **mutation 驗證**（`/opt/tmp/verify/20260820-sqlexecutor-mutation.log`）：
  拿掉「org 覆寫拒絕」「SECURITY DEFINER 檢查」「READ ONLY 交易」「跨企業過濾」
  四道防線，對應測試各自變紅 —— 測試不是恆真斷言
- 開發庫實測（`/opt/tmp/verify/20260820-sqlexecutor.log`）：
  跨企業拿到不同資料、竄改 config 帶 org 被拒、白名單外的 code 被拒、
  未宣告參數被拒、SQL 片段當值不當語法、唯讀交易擋下 INSERT、statement_timeout 生效
- 瀏覽器實測（VERIFY-01）：設計器面板載入白名單、已存的 `procedure_code`
  正確 selected、參數欄位依 SP 動態重畫、`collectSqlExecutorConfig()` 原樣回收設定、
  console 無錯誤
