# NoCode Builder 解除隱藏前資安盤點（2026-09-13）

背景：`nocode_builder` 選單自 2026-08-07 起隱藏（`NOCODE_BUILDER_MENU` 未設；DB 三筆選單今日查證**已不存在**，非文件所述 `is_deleted=true`），
Ethan 打算解除隱藏並明文告知讀者「未完成、考慮移出、建議別用」。本檔是解除前的盤點與修復建議。
機械檢查與實測輸出：`/opt/tmp/verify/20260913-nocode-unhide-audit.log`；測試基準：`/opt/tmp/verify/20260913-nocode-tests-baseline.log`（295 passed / 1 skipped）。

## 一、先講結論

1. **隱藏沒有保護任何東西**。下面所有 P1 今天就存在，攻擊者不需要選單。解除隱藏只改變「誰會注意到」。
2. **P1 共 5 條，全部集中在「管理端 API 的授權粒度」**，與 portal 公開面無關。portal 匿名面（15 個 `@public_route`）的授權鏈、fail-closed、CSRF、IDOR 逐條查過沒有破口。
3. 若決定保留模組：P1 全修再解除隱藏。若決定移出：至少修 P1-1／P1-2（成本最低、暴露面最大），其餘以「預設停用」處理。

## 二、統計

| 面 | 數量 | 來源 |
|---|---|---|
| 端點（守門宣告表，含 web／api／portal） | 143 | `route_guard_table.yaml` |
| API 端點分級（PF-145 稽核腳本） | A 11 / B 55 / C 1 / D 46 / E 1 | `scripts/audit_module_api_gates.py` |
| portal 匿名可達端點 | 15（`@public_route`），其中 4 個有限流 | `web/portal_public.py` |
| semgrep `beakplatform-sql-injection` | 8 命中，**8 個假陽性**（表名皆為程式內常數） | 見 log [3] |
| `Model.query` 在 api/ | 24，其中 4 處無 org 條件（見 P2-5） | 見 log [8] |
| 隱藏期間本模組 commit | 8（皆為平台橫向變更帶到） | `git log --since=2026-08-07` |
| 相關測試 | 295 passed / 1 skipped | baseline log |

## 三、P1（解除隱藏前必修；今天已可被同企業任一登入帳號利用）

### P1-1 `rows` CRUD 端點只驗合約，不驗 ACL，寫入時子系統檢查可被省略
`api/__init__.py:750 / 811 / 873`（create／update／delete_row）與 `:606`（query_rows）
decorator 是 `@module_access_required('nocode_builder', False)`（check_acl=False，A 級）。
`_check_sub_system_crud()`（`:1256-1277`）在沒送 `X-SubSystem-SC` header 時 `return None` 放行。
**實測**：BELUGA 的 EXTERNAL 廠商帳號 `gg@gmail.com`（無 ACL、無 SUBSYS_DESIGNER）
`GET /api/nocode-builder/views/<sc>` → 403（ACL 生效），但 `GET .../rows?sub_system_sc=<ss>` → **200 回資料**。
寫入端點同一道閘門，`allow_create/edit` 在 `resolve_view` 自建的視圖預設為 true。
修法：rows 四支改 `check_acl=True`（與同檔其他端點一致），`_check_sub_system_crud` 缺 context 時不放行而是退回 view 所屬子系統判定。

### P1-2 SQLite 路徑的 `sub_system_sc` 來自 query string，未比對 view 所屬
`api/__init__.py:614 / 671 / 787 / 848 / 909`：`ss_sc = request.args.get('sub_system_sc') or _resolve_sub_system_sc(view)`，
`_resolve_sub_system_sc` 也是先信 header／param。`DataSourceManager` 純依字串開檔（`data_source_manager.py:63-73,104-131`），不查擁有權。
後果：拿到任一子系統 secure_code（portal 公開 URL 會出現）就能把讀寫目標換成該子系統的 `portal.db`／`portal_data.db`，跨子系統、理論上跨企業。
修法：一律由 view 反查所屬子系統（DB），request 給的值只允許等於反查結果。

### P1-3 portal 權限管理 12 支寫入端點缺「開發者／管理員」檢查
`api/portal_permission_api.py`（9 支）、`api/portal_org_api.py`（3 支）只掛 `@module_access_required('nocode_builder')`，
內部 `_get_owned_sub_system()` 只驗子系統屬於本企業。對照 `site_map_api.py` 同類端點都有 `_check_developer()`。
後果：任何持 nocode ACL 的員工可改企業內**任一**子系統的 portal 角色、階級、使用者權限覆寫。
修法：補 `_check_developer()` 或掛 `@permission_required('nocode_builder.manage')`（D2）。

### P1-4 ACL 持有者可枚舉企業庫全部表、對 form_workflow 同步表建可刪視圖
- `api/sub_system_api.py:437 / 495 / 536 / 645`（data-sources／tables／resolve-view／columns）只有 module ACL，無 developer 檢查，
  同檔 `:689 create_portal_data_table` 卻有掛 `@permission_required('nocode_builder.manage')`，明顯漏掛。
- `schema_service.list_tables()` 不排除其他模組的表，還特別標 `is_approval_table`（`:34-36,96`）——作者知道 `<table>_approvals` 在同一庫。
- `crud_service.delete_row()`（`:497-524`）沒有 approvals／系統表守門；`_is_system_column` 只保護 create/update。
- `crud_service.py:276`：`visible_cols` 為空時 fallback 成 `SELECT *`——approvals 表所有欄位都 `visible=False`，結果反而全部吐出。
- `bfsync_<id>` 對 `org_<id>` 全部表有 DML（`org_db_manager.py:272-283` DEFAULT PRIVILEGES），DB 層擋不住。
修法：四支補 manage 權限；`list_tables` 加排除清單（至少 `_approvals` 與非 nocode 建立的表）；`delete_row` 比對系統表；`SELECT *` fallback 改為拒絕。

### P1-5 資料橋接可把企業庫任意表搬進公開 `portal_data.db`，無 egress
`services/data_bridge_service.py:93-192`（publish/update）`source_table` 由 body 提供，`_validate_params()`（`:769-777`）只驗識別符格式；
`collect()`（`:299-397`）的 `context` 白名單不限制 `target_table`。整條路徑無 `egress_service.apply()`。
觸發者是子系統 `developers`（`_check_developer_access`）。
修法：source/target 限定為該子系統擁有的表（登記表或命名前綴），並過 egress。

## 四、P2（解除隱藏後暴露面擴大才變重要，或需前提）

| # | 問題 | 位置 | 說明 |
|---|---|---|---|
| P2-1 | portal 登入無專屬限流、無失敗鎖定；註冊無限流；rows CRUD 三支無限流 | `portal_public.py:1417,1471,614,1265,1309`；`portal_auth_service.py:157-202` | 只吃全站預設 6000/min。平台自身登入是 5/min。可線上撞庫、高速枚舉帳號（註冊回「此帳號已被使用」） |
| P2-2 | portal 登入後不換 session id | `portal_auth_service.py:49-54` | 與平台共用 `beakmask_session` cookie，只做命名空間隔離；平台跑 http，session fixation 前提較易成立 |
| P2-3 | 表頭 label 未轉義塞 innerHTML | `datalist-widget.js:440-446`、`formgrid-widget.js:727-733` | 儲存型 XSS，設計者→同企業檢視者。只載入於內部 `sub_system_portal_v2.html`（`check_acl=False`），公開 portal 走 `pageir.js`（0 處未轉義）。資料列用 textContent 是安全的 |
| P2-4 | 4 個模板動作按鈕未包 `can()`、未注入 `__PAGE_CAPS` | `sub_system_list.html`、`sub_system_config.html`、`lookup_manager.html`、`my_projects.html` | 後端 `@admin_required` 有擋（點了 403），只是 UX 誤導；違反 PERM-02 |
| P2-5 | 子系統 crud 檢查用無 org 條件的 `DcSubSystem.query`，且 `is_org_admin` 直接判 MANAGER | `api/__init__.py:1290,1301,1336,1391`；`sub_system_service.py:60-76` | 他企業 ORG_ADMIN 對任意 sub_sc 被判為 MANAGER；最終寫入對象仍受 view 租戶隔離，屬授權判定汙染 |
| P2-6 | **解除隱藏後的功能回歸**：Key1 只給 ORG_ADMIN，靠 ACL 進來的 EMPLOYEE 開 `/nocode-builder/sub-systems`、`/lookup` 會被 PageRoleGuard **強制登出** | `__init__.py:20`（user_types）、`page_role_guard.py:97-107,184` | BELUGA 現有一名 EMPLOYEE 持 SUBSYS_DESIGNER＋ACL 會撞到。既有企業 Key2 也不會自動補（`MENU_ROLE_DEFAULTS` 只在建企業時套用） |

## 五、P3（規範不符，低風險）

- NET-01：`portal_public.py:784`、`web/__init__.py:508` 用 `request.remote_addr`（稽核欄位）。
- `portal_logout` `@csrf.exempt`（可被 CSRF 強制登出）。
- `nocode_builder.view` 權限碼從未被檢查（死碼）。
- `portal.db` 建檔未 `chmod 600`（含 `portal_users.password_hash`）。
- 四個 SQL helper 靠呼叫端自律不驗 identifier（semgrep 會持續誤報）。
- `docs/manual` 零篇提到 nocode，解除後不會有過時文件出現；`NOCODE_MENU_HIDE.md` 步驄 2 的 UPDATE 現在影響 0 筆（可省）。

## 六、與 PF-145 的關係

PF-145 第 5 項明寫：「nocode_builder 全部 B 級 55 支，NoCode 選單隱藏中，page_keys 對不存在選單 fail-closed，掛了全擋死，等選單復原或改走 D2 判準，另案」（`PF145_MODULE_API_KEY1_AUDIT.md:400`）。
解除隱藏就是那個「另案」的觸發條件。但本盤點顯示最嚴重的不是 B 級（B 級至少有 ACL），而是 A 級的 rows 四支與 B 級中漏掛 developer 檢查的 16 支。

## 七、建議的處置順序

| 順序 | 內容 | 規模 | 前置 |
|---|---|---|---|
| 1 | P1-1＋P1-2（rows 四支 check_acl=True、sub_system_sc 由 view 反查） | 小（同檔約 30 行） | 無 |
| 2 | P1-3＋P1-4 前半（16 支補 `_check_developer` 或 manage 權限） | 小～中 | 無 |
| 3 | P1-4 後半（list_tables 排除、delete_row 守門、SELECT * fallback） | 中 | 決定「nocode 能不能碰非自建表」 |
| 4 | P1-5（橋接表範圍限制＋egress） | 中 | 同上 |
| 5 | P2-6（Key1 user_types 或 ACL bypass）→ 解除隱藏 | 小 | 1～4 完成 |
| 6 | P2-1～P2-3 | 小 | 可與解除同批或後補 |

若最終決定移出模組：做 1、2，其餘改為 `MODULE_INFO['enabled']` 吃環境變數、出廠預設關閉，文件寫明。
