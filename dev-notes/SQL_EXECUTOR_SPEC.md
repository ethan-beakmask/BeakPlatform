# SysSqlExecutor 節點規格與安全設計（2026-08-20 第一版）

## 2026-09-13 更名（PF-254 第一階段）

原 `SqlExecutor` 節點已更名為 `SysSqlExecutor`，成為系統級受限節點
（`org_restricted=true`），設計器分類從「整合」移到「系統」。出廠只授權系統預設企業，
一般企業未取得授權時在設計器看不到這個節點——**這是預期狀態，不是缺陷**。
連的仍是平台主庫，這對系統級節點是正確的。

未獲授權企業的行為：`/api/workflows/data/sql-procedures` 回 403；
graph 帶該節點寫入回 403「流程中含有本企業未獲授權的節點型別」
（`api/graph_authz.py`）；執行期由 `node_runner` 統一擋，
handler 的 `handle()` 開頭另有一道 `is_node_allowed()` fail-closed 最後防線。

**既有環境升級**：`venv/bin/python scripts/migrate_sqlexecutor_to_sys.py --apply`
（`--dry-run` 是預設，冪等，重跑全 0）。它做七件事：節點定義、企業授權紀錄、
`graph` 與 `cytoscape_config`、發行快照、執行佇列與執行紀錄的 node_type 字串、
系統企業出廠授權，以及**節點 icon 路徑**。

> **icon 那段不能省。** 更名時 `sqlexecutor.svg` 已 `git mv` 成 `syssqlexecutor.svg`，
> 而 icon 路徑是**存在每個節點自己的 `icon` 欄位裡**、不會隨 node_type 一起換。
> 漏了就是設計器畫布上該節點破圖，而畫面沒有任何錯誤訊息（2026-09-13 實際踩到，
> 第一版遷移腳本漏了這段，是瀏覽器實測才發現的）。
> 替換**依 node type 分流、不做無差別字串取代**：SQL 節點導到 `syssqlexecutor.svg`，
> `AiAgent` 導到 `aiagent.svg`（舊 graph 裡 AiAgent 借用過 `sqlexecutor.svg`，
> 見 `dev-notes/WORKFLOW_DESIGNER_NOTES.md`），其餘型別不動。

**企業級 SQL 節點（連企業專屬庫 `org_<id>`）是第二階段，鐵人賽之後再評估，現在不做。**
延後的理由不是「現在有洞」而是風險耦合（PostgreSQL 的提權途徑目前全關，
但那是可能為了別的需求被打開的外部變數）——完整脈絡與七項殘餘攻擊面見 BBN `PF-254`。

流程節點型別 `SysSqlExecutor`：讓流程呼叫**平台主庫裡事先登錄過**的 stored procedure，
把結果寫進流程變數，可再插一筆簽核註記給人類參考。
典型場景：請料單在核可前先查庫存夠不夠，不夠就在簽核意見提醒。

| 檔案 | 角色 |
|---|---|
| `modules/form_workflow/services/node_handlers/sys_sqlexecutor_handler.py` | handler（安全核心，檔頭有完整設計說明） |
| `modules/form_workflow/models/sql_procedure.py` | 白名單 model `FwSqlProcedure` |
| `scripts/migrations/legacy/106_sqlexecutor_whitelist.sql` | schema `fw_sp`、白名單表、範例 SP 與範例資料 |
| `modules/form_workflow/api/workflows.py::get_sql_procedures` | 設計器下拉用的清單 API |
| `modules/form_workflow/static/.../js/wf-node-sys-sql-executor.js` | 屬性面板 |
| `backend/tests/test_sys_sqlexecutor_node.py` | 47 個測試（含四道防線的 mutation 驗證） |

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

**登錄一筆 ＝ 授權流程設計者呼叫那支 SP，屬於部署期決定**，所以走 SQL 檔
而非 Web UI。（2026-09-01 PF-168 起 migration 制度廢止：一次性 SQL 對 dev 庫
執行後歸檔 `scripts/migrations/legacy/`；`fw_sp` schema 本身由安裝資產
`scripts/sql/fw_sp_setup.sql` 建立。下文提到「migration」的地方一律照此理解。）

**2026-08-31（migration 133）起 `fw_sp` 的 owner 是 NOLOGIN 角色 `fw_sp_owner`，
`beakplatform` 只有 USAGE + EXECUTE**——所以建 SP 的 migration **必須用 postgres 跑**
（`sudo -u postgres psql -d beakplatform_dev -f ...`），用 beakplatform 跑會
`permission denied for schema fw_sp`。建完要把 ownership 交回 `fw_sp_owner`
並明確授 EXECUTE（見步驟 1b）。

新增一支 SP 的完整步驟：

```sql
-- 1) 函式建在 fw_sp，第一個參數固定 p_org_secure_code，且必須是實際 filter 條件。
--    表引用一律 schema 限定（public.xxx）——執行時 search_path 釘死為 pg_catalog
--    （P3-2），沒限定的執行時直接 relation not exist
CREATE OR REPLACE FUNCTION fw_sp.my_query(p_org_secure_code TEXT, p_x TEXT)
RETURNS TABLE (col_a VARCHAR, col_b NUMERIC)
LANGUAGE sql STABLE SECURITY INVOKER   -- 不可以是 SECURITY DEFINER
AS $$
    SELECT t.col_a, t.col_b FROM public.some_table t
    WHERE t.org_secure_code = p_org_secure_code   -- 租戶邊界
      AND t.x = p_x;
$$;

-- 1b) ownership 交給 fw_sp_owner、EXECUTE 只給 app role（PF-190 P3-1）
--     （用 postgres 跑時 CREATE 出來的 owner 是 postgres，一律明確轉移）
ALTER FUNCTION fw_sp.my_query(TEXT, TEXT) OWNER TO fw_sp_owner;
REVOKE ALL ON FUNCTION fw_sp.my_query(TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fw_sp.my_query(TEXT, TEXT) TO beakplatform;

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

## 開發機上的兩個可操作範例（2026-08-20 建置）

`scripts/examples/provision_node_demo_flows.py --apply` 會把 beluga 的兩個空流程
改造成可以在 `/forms/center` 走完全程的示範（冪等，重跑會重新發行）：

| 流程 code | 表單 | 示範內容 |
|---|---|---|
| `WF2610385E` | 請料單（SysSqlExecutor 範例） | 送單 → 查庫存 SP → 依「足夠／不足／查無料號」三分流 → 主管核可 |
| `WF052334D2` | 可疑內容送審（AI 分析範例） | 送單 → AI 分析 → 依 verdict 分流 → 人工確認 |

兩者的簽核者都是 `assignee_type='INITIATOR'`（發起人自己），
一個帳號就能走完全程，不必先安排角色。

**四件不做就會卡住、而且症狀看起來像壞掉的事**：

1. **填寫權限**：表單中心的填寫權限預設只放行 SYSTEM_ADMIN 與
   FLOW_DESIGNER / FORM_DESIGNER 角色（`fill_permission_service`），
   **ORG_ADMIN 不在內**。沒有 `fw_mapping_permissions` 記錄時，
   連企業管理員送單都會拿到「您沒有填寫此表單的權限」。
   腳本會逐一授權給企業內非 EXTERNAL 的在職帳號
2. **改 graph 要 bump revision**：publish 靠 version+revision 判斷有無變更，
   直接改 `graph` 不會自動 bump，不 bump 就會沿用舊快照
3. **變數樣板沒有條件語法**：把庫存數字放進 SysSqlExecutor 的 `note_template`，
   查無料號那條會印出「現有庫存  ，安全存量 」。條件性的措辭要交給
   分流之後的 OpFieldWrite 節點，註記只放三條路都成立的事實
4. **`graph` 與 `cytoscape_config` 兩個欄位都要寫**：引擎讀前者、設計器讀後者
   （後者優先）。只寫 `graph` 的話流程跑新版、設計器畫舊版，**不會有任何錯誤訊息**。
   詳見 CLAUDE.md「用腳本產生流程 graph 時的三個坑」

### 端對端實測（經由真正的 executor，不是直接叫 handler）

| 送單 | 分流 | 表單欄位 | 簽核註記 |
|---|---|---|---|
| A-1002 × 500（庫存 80） | 庫存不足 | `[庫存不足，請確認是否仍要核可] …` | `查得 1 筆` |
| A-1001 × 10（庫存 1200） | 庫存足夠 | `[庫存充足] …` | `查得 1 筆` |
| ZZ-9999 × 1 | 查無此料號 | `[查無此料號] …` | `查得 0 筆` |
| 含 SQLi + prompt injection 的 HTTP request | 有風險 | `[AI 判定：malicious，風險分數 95，規則層命中 2 項]` | 系統警示 + AI 說明 |

## 已知限制與後續

- **只支援唯讀**（見上）
- **白名單沒有管理 UI**，新增走 migration
- `fw_sp` 內的函式若有同名多載，handler 會拒絕執行（無法判定要呼叫哪一個）
- 設計器的拖放與存檔仍只做過 DOM 層驗證（面板渲染、設定回收），
  沒有真的用滑鼠拖一個節點出來存檔

## 驗收紀錄

- 單元／整合測試：47 passed（`bash scripts/run_tests.sh tests/test_sys_sqlexecutor_node.py -q`）
- **mutation 驗證**（`/opt/tmp/verify/20260820-sqlexecutor-mutation.log`）：
  拿掉「org 覆寫拒絕」「SECURITY DEFINER 檢查」「READ ONLY 交易」「跨企業過濾」
  四道防線，對應測試各自變紅 —— 測試不是恆真斷言
- 開發庫實測（`/opt/tmp/verify/20260820-sqlexecutor.log`）：
  跨企業拿到不同資料、竄改 config 帶 org 被拒、白名單外的 code 被拒、
  未宣告參數被拒、SQL 片段當值不當語法、唯讀交易擋下 INSERT、statement_timeout 生效
- 瀏覽器實測（VERIFY-01）：設計器面板載入白名單、已存的 `procedure_code`
  正確 selected、參數欄位依 SP 動態重畫、`collectSysSqlExecutorConfig()` 原樣回收設定、
  console 無錯誤

---

## 附：從 CLAUDE.md 移入的三條硬規則（2026-08-30）

節點型別 `SysSqlExecutor`，handler
`modules/form_workflow/services/node_handlers/sys_sqlexecutor_handler.py`。
**完整規格與「怎麼加一支新 SP」看 `dev-notes/SQL_EXECUTOR_SPEC.md`，動這個模組前整份讀完。**

留在本檔的是三件猜不到、猜錯就是漏洞的：

- **節點設定存在 `fw_workflow_templates.graph`，而 graph 可以用 API 直接 PUT 改寫。**
  所以設計器的下拉選單不是防線 —— handler 拿 config 的 `procedure_code`
  去 `fw_sql_procedures` **重查一次**（含企業歸屬、`is_active`），查不到就拒絕。
  同理參數也依白名單登記的型別重新驗證。這道漏了等於白名單不存在
- **只能呼叫 schema `fw_sp` 內的函式，schema 名是 handler 的字面常數**。
  不要為了方便改成可指定 schema —— 那等於開放 `pg_catalog`
- **org 過濾靠的是 SP 自己的 `WHERE`，不是 RLS**。平台主庫只有 10 張表有 RLS
  且都不是 FORCE，`beakplatform` 又是 owner（owner 不受自己的 policy 限制）。
  每支 SP 的第一個參數固定 `p_org_secure_code`，由 handler 從流程所屬企業帶入；
  config 裡出現這個參數名一律**整次拒絕**（不是忽略）

**v1 刻意只支援唯讀**：`_execute()` 一律 `SET TRANSACTION READ ONLY`，
由資料庫層保證這個節點寫不了東西。要支援寫入型 SP 必須先回答交易語意問題
（同交易則 SP 內不能 COMMIT；獨立交易則流程失敗時副作用留著），
**不是把那一行拿掉**。

白名單維護走 migration（`scripts/migrations/legacy/106_sqlexecutor_whitelist.sql`），
**刻意不做 Web UI** —— 登錄一筆等同授權。

**改 handler 後 executor 要重啟才認得**（`beakplatform-dev-executor` 是獨立進程）。

---

## 已驗證的隔離邊界（2026-08-31 紅隊測試）

Session B 對「企業只能讀自己的資料庫、讀不到別企業與其他系統的庫」做了紅隊測試。
**結論：無 P1（無可跨企業/跨系統讀資料的路徑），租戶隔離結構性成立。**
完整輸出 `/opt/tmp/verify/20260831-sqlexecutor-isolation.log`，
自動化測試 `backend/tests/test_sys_sqlexecutor_isolation.py`（34 條，與 `test_sys_sqlexecutor_node.py` 互補）。

### 為什麼 SysSqlExecutor 碰不到別的資料庫（結構性，非靠自律）

四件疊在一起，缺任何一件都不會有跨庫路徑：

1. handler 寫死 `db.engine`（= 主庫），沒有第二個 engine
2. PostgreSQL **不支援 cross-database references**（`dbname.schema.table` 直接被拒）
3. 主庫沒有 `dblink` / `postgres_fdw` / `file_fdw`，且 `beakplatform` **不是 superuser、
   不能 `CREATE EXTENSION`**、`pg_read_file` / `COPY FROM PROGRAM` 皆 permission denied、
   不屬任何 `pg_*` 特權角色（含 `pg_read_all_data`）
4. 企業獨立庫 `org_<id>` 對 `beakplatform` **直接拒絕 CONNECT**

### org 邊界的傳遞鏈（config / graph / 快照都改不動它）

`SP 的 p_org_secure_code ← queue_item.org_secure_code ← workflow_instance.org_secure_code
← form_instance.org_secure_code ← get_current_org()（登入 session，非 request body）`

- workflow template 與 subflow 都以「表單/父流程的 org」過濾，跨企業引用 → `ValueError`
- **org 不在 graph 裡**：即使 graph 或發行快照被別家企業共用，SP 收到的仍是提交者
  自己企業的 org，回自己企業的資料。這是設計最強的一點
- handler 所有檢查（`_load_procedure` / `_verify_function` / `_build_params`）都在**執行期**跑，
  快照路徑與 live graph 走同一個 `handle()`，沒有「可信快照」旁路

### 重測指令（數字與清單會腐爛，跑指令不要信結論數字）

```bash
PS="PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev"

# 1) DB role 邊界：全部應為 f（非特權），且無 dblink/fdw
$PS -c "SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname='beakplatform';"
$PS -c "SELECT extname FROM pg_extension;"   # 不應出現 dblink / postgres_fdw / file_fdw
$PS -c "SELECT pg_read_file('/etc/passwd',0,10);"          # 應 permission denied
$PS -c "SELECT * FROM postgres.public.x LIMIT 1;"          # 應 cross-database references not implemented

# 2) fw_sp 每支函式必須以 p_org_secure_code 為唯一租戶邊界（逐支看 WHERE）
$PS -c "SELECT p.proname,p.prosecdef FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='fw_sp';"
$PS -t -c "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='fw_sp' ORDER BY p.proname;"
# prosecdef 必須全 f（非 SECURITY DEFINER）；每支 WHERE 必須有 org_secure_code = p_org_secure_code

# 3) 白名單每筆第一參數必須是 p_org_secure_code，function_name 必須存在
$PS -c "SELECT code,org_secure_code,parameters->0->>'name' first_param,
  EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='fw_sp' AND p.proname=s.function_name) fn_exists
  FROM fw_sql_procedures s WHERE is_deleted=false;"

# 4) 自動化測試（互補於 test_sys_sqlexecutor_node.py）
bash scripts/run_tests.sh tests/test_sys_sqlexecutor_isolation.py -q

# 5) 叢集內其他庫的實際暴露面（P2 用；不要只看 CONNECT，要看有幾張表真的讀得到）
for d in $(PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A \
    -c "SELECT datname FROM pg_database WHERE datistemplate=false AND datname<>'beakplatform_dev';"); do
  echo -n "$d -> "
  PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d "$d" -t -A -c \
    "SELECT count(*) FROM information_schema.tables t
     WHERE t.table_schema NOT IN ('pg_catalog','information_schema')
       AND has_table_privilege(quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),'SELECT');" 2>&1 | tr '\n' ' '
  echo
done
```

### 待決策（非 SysSqlExecutor 本身，但直接關乎「讀到別的系統的庫」）

- **P2**：`beakplatform` role 對同一個 PostgreSQL 叢集上的其他資料庫有 CONNECT 權限
  （PUBLIC 預設）。SysSqlExecutor **用不到**（跨庫不支援，見上方四點），但這是主機層的
  資料暴露面，而且**不是空的**——2026-08-31 主 Claude 用 `has_table_privilege` 實測：

  | 庫 | 以 `beakplatform` 身分實際可 SELECT 的表數 |
  |---|---|
  | `beakplatform`（**退役的正式環境庫**） | **97**（活體讀出 `users` 4 筆） |
  | `vulnmgmt` | **19**（`assets` / `vuln_definitions` / `audit_log` 等） |
  | `test_temp` | 12 |
  | `forgejo` / `google_gmail_db` / `beak_broodnest` / `xff_intel` | 0（有 CONNECT，無可讀表） |
  | `org_106`（企業獨立庫） | **拒絕 CONNECT** —— 這條做對了 |

  **Session B 原本回報「那些庫 public schema 0 張可讀表」是錯的**，只對後面那四個成立。

  **根因不是 CONNECT 權限鬆，是 ownership**（2026-08-31 續查）：

  | 資料庫 | db owner | 那些可讀表的 owner |
  |---|---|---|
  | `beakplatform`（退役正式庫，21MB） | **`beakplatform`** | `beakplatform`（97 張全部） |
  | `vulnmgmt`（25MB） | **`beakplatform`** | `beakplatform`（14 張） |
  | `test_temp`（18MB） | **`beakplatform`** | `beakplatform`（8 張） |
  | `beakplatform_dev`（本專案實際在用的） | `beakmask` | — |
  | `forgejo` | `beakmask` | — |

  也就是說 **`beakplatform` 這個 DB role 同時是另外三個資料庫的 owner**，
  它讀得到那些表不是因為誰把權限開太鬆，而是那些表本來就是同一個帳號建的。
  **所以 `REVOKE ... FROM PUBLIC` 對這個情況無效**——owner 的權限 revoke 不掉
  （它可以自己 GRANT 回來）。正確處置只有兩種：

  1. 退役的 `beakplatform` 庫 → `pg_dump` 留底後 **`DROP DATABASE`**（Ethan 2026-08-31
     判定該庫已無存在必要；最後一筆 users 是 2026-04-20，4 個帳號 2 家企業）
  2. `vulnmgmt` / `test_temp` → 那是別的專案的庫，**共用同一個 DB 帳號才是根因**。
     要隔離就得讓各專案各自持有獨立的 DB role。屬主機層架構決定，不是本專案單方面能改。

  **處置結果（2026-08-31 當天）**：

  - 第 1 項**已執行**——`beakplatform` 庫已 `DROP DATABASE`（備份與還原演練記錄見
    `/opt/tmp/verify/20260831-drop-retired-db.log`，dump 在
    `/opt/tmp/backup/beakplatform-retired-db-20260831/`）。
    暴露面從 3 個庫 128 張表降到 2 個庫 31 張表，含 `users` 的那 97 張已消失
  - 第 2 項 Ethan 決定**保持現況**（歷史債、無緊急性）。
    **不要再把 `vulnmgmt` / `test_temp` 的共用 owner 提報為缺陷。**
  重測：見上方重測指令第 5 條（那條只看得到「讀得到幾張表」，
  要看根因要另外查 `pg_get_userbyid(datdba)` 與 `pg_tables.tableowner`）。
- **P3-1【已完成 2026-08-31，migration 133】**：`fw_sp` schema 與函式改由
  NOLOGIN 角色 `fw_sp_owner` 擁有，`beakplatform` 只剩 USAGE + EXECUTE
  （CREATE / REPLACE / DROP / ALTER 實測全數 permission denied，
  憑證 `/opt/tmp/verify/20260831-pf190-p31.log`）。配套：
  新增 SP 的 migration 從此必須用 postgres 跑（見「白名單維護」步驟 1b）；
  default privileges 的 REVOKE 用全域形式——schema 範圍的
  `ALTER DEFAULT PRIVILEGES ... IN SCHEMA ... REVOKE` 收不掉內建的
  PUBLIC EXECUTE（只能增不能減，實測無效）。
  另注意：三支 demo SP 引用的 `fw_demo_inventory` 已被 migration 118
  （PF-169 dev 清理）刪除，dev 環境呼叫它們會報 relation not exist，
  與本變更無關、早已如此。
- **P3-2【已完成 2026-08-31】**：`_execute` 唯讀交易內以
  `set_config('search_path', 'pg_catalog', true)` 釘死 search_path。
  **連帶要求：SP 內表引用必須 schema 限定（`public.xxx`）**，未限定者執行時
  直接 relation not exist——這從建議升格為硬約束，測試
  `test_search_path_pinned_unqualified_table_fails` 釘住。
- **P3-3【已完成 2026-08-31】**：integer/numeric 正則 `\d` 改 `[0-9]`，
  全形數字從「安全轉換」改為「直接拒絕」（原釘住現況的測試已改為斷言拒絕）。
