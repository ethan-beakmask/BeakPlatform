# 權限管理中心（Access Center）規格書

Phase C 新權限管理 UI。2026-07-17 與用戶定案。
本文件是 Codex 實作的唯一依據；工作包（WP1~WP5）依序實作，每包獨立可驗收。

## 1. 目標

以單一入口 `/access/`「權限管理中心」取代四個分散的舊權限 UI：

| 退役對象 | 現有功能 | 去向 |
|---|---|---|
| `/permissions/` 權限中央三 tab | 角色視角 RBAC 勾選、功能視角 Key2 編輯、衝突偵測 | Tab2 / Tab1 / Tab4 |
| `/roles/` 角色管理 | 角色 CRUD | Tab2（與 RBAC 勾選合併） |
| `/admin/account-roles/` | 帳號角色指派大表 | Tab3 |
| `/menu/` 編輯頁的鑰匙區塊 | Key1 user_type 勾選、Key2 角色設定 | Tab1（/menu/ 瘦身為純結構編輯） |

**上線即退役，不可並存**（雙倍維護是現況混亂成因）。
例外：`/menu/` 的「建立」頁保留 user_type 初始勾選（新選單建立即種 Key1，避免 fail-closed 造成誰都看不到）；「編輯」頁的鑰匙1/鑰匙2 區塊全部移除。

## 2. 名詞與權限模型（實作前必讀）

- **雙鑰匙**：Key1 = `menu_permissions`（user_type 四層可見性），Key2 = `menu_role_requirements`（org+menu+role）。EMPLOYEE/EXTERNAL 需同時通過；SYSTEM_ADMIN / ORG_ADMIN / 原始管理員 bypass（`PageRoleGuard`）。
- **RBAC**（`permissions` + `role_permissions`）：僅在 API/資源層執法；`menu_items.required_permission` 已退役，不影響選單。
- **角色名詞定版**：見 `dev-notes/ROLE_TAXONOMY.md`。`role_level`、互斥群組 `exclusive_group`（IDENTITY_TYPE 全域互斥 / DEPT_POSITION、GROUP_POSITION 同 unit 互斥）。
- **user_type 硬界線**：角色永不跨層。

## 3. 路由與選單

### Web 路由
- 新檔 `backend/app/web/access_center.py`：blueprint `access_center`，註冊於 `backend/app/web/__init__.py`，`url_prefix='/access'`。
- 單一路由 `GET /` → `render_template('pages/access_center/index.html', ...)`。
- **不掛身分 decorator**（Phase B「選單即授權」模式：url 型選單 `/access/` 前綴領地由 PageRoleGuard 把關）。模板內以 `current_user.is_system_admin` 決定視角。

### 選單（migration，WP1 建、WP5 退役舊項）
- 新增兩筆 url 型選單（同 URL 分屬兩個 user_type，仿 permission_central 現況雙選單模式）：
  - `access_center`：title「權限管理中心」，parent=`perm_mgmt`（權限管理群組），Key1=SYSTEM_ADMIN
  - `access_center_org`：title「權限管理中心」，parent=`roles_control`（角色管控群組），Key1=ORG_ADMIN，Key2 複製 `users` 選單的各企業 ORG_ADMIN 角色
  - link_type=`url`、link_target=`/access/`、title_i18n `{"en": "Access Center"}`
- WP5 軟刪選單：`permission_central`、`permission_central_org`、`roles`、`account_roles`（menu_items 設 is_deleted + menu_defaults 刪列），並同步 `menu_defaults` 新增 access 兩筆。

## 4. 前端架構

- 模板：`backend/app/templates/pages/access_center/index.html`（主框架 <200 行）+ partial 每 tab 一檔：
  `_tab_functions.html`、`_tab_roles.html`、`_tab_accounts.html`、`_tab_health.html`（各 <500 行，FRONT-02）
- JS：`backend/app/static/js/access-center/`：`main.js`（tab 切換 + 共用 fetch/csrf helper）、`functions.js`、`roles.js`、`accounts.js`、`health.js`（模式 B window bridge：模板只注入 `window.__AC_CONFIG = { isSystemAdmin, orgCode, ... }`）
- CSS：`backend/app/static/css/access-center.css`，class 一律 `ac-` 前綴
- **平台無 Bootstrap**（FRONT-07）：排版用 CSS Grid/Flexbox；按鈕 `.btn`、表格 `.data-table`、表單 `.form-control`、Modal `.modal-overlay` 用 common.css 既有元件；禁止 `row`/`col-*`/`card`/`mb-3`/`d-flex` 等 Bootstrap class
- Alpine.js：Modal 禁用 `@click.away`；`x-for`/`x-if` 直接子節點必須單一 element；有 `x-show` 的元素禁止 inline `display`（FRONT-06）
- i18n（I18N-01）：所有 user-facing 字串——模板 `{{ _('中文') }}`、JS `__('中文')`（i18n.js 全域已載）、Python flash/error `_('中文')`。禁止包裹 console/log/DB 值/比較用字串
- 時間顯示：JS 一律 `BkTime.format(iso, 'short')`，禁 `toLocaleString`（TZ-01）
- CSRF：非 GET fetch 帶 `X-CSRFToken`（從 `<meta name="csrf-token">` 取；main.js 提供共用 helper）

## 5. Tab 規格

### Tab1 功能授權（`functions.js` + `_tab_functions.html`）

佈局：左側選單樹（含 header 群組節點）+ 右側授權面板（`ac-grid-2` 雙欄，左窄右寬）。

- 資料來源：`GET /api/permissions/menus`（權限中央現有 API，含樹與 user_types）；若現有回應缺欄位可擴充該 API（不破壞舊格式）
- 右側面板（選中選單後顯示）：
  1. **鑰匙1 user_type**：四個 checkbox。SYSTEM_ADMIN 可編輯（呼叫新 API `PUT /api/menu/<sc>/permissions`，見 §6）；ORG_ADMIN 唯讀顯示
  2. **鑰匙2 角色**：
     - SYSTEM_ADMIN：以角色 code 勾選，PUT 批量套用所有企業（沿用 `GET/PUT /api/menu/<sc>/roles` 現有雙模式邏輯）。**必須保留高風險警示**：儲存前 confirm 顯示「將批量套用到全部 N 個企業」
     - ORG_ADMIN：本企業角色（含自訂角色）勾選，同 API 的 org 模式
  3. header/divider 型選單：鑰匙2 區塊隱藏（結構節點不吃 Key2，與現況一致）；鑰匙1 照常
- 樹節點顯示 Key1 摘要徽章（如「管+員」）方便掃視

### Tab2 角色（`roles.js` + `_tab_roles.html`）

- 角色列表（`GET /api/roles/`）：名稱、code、類型、範圍、系統角色徽章、使用人數、啟用狀態
- SYSTEM_ADMIN：企業下拉（沿用權限中央 `org_code` 參數模式）選定後操作該企業
- 建立/編輯（Modal，寬 ≥600px）：
  - 屬性欄位：name、code（建立時可留空自動產生，走 `/api/roles/generate-code`、`validate-code`，FRONT-04）、role_type（ROLE/POSITION）、scope_type（GLOBAL/DEPARTMENT/GROUP/EXTERNAL）、is_manager、description、sort_order、is_active
  - **exclusive_group 下拉**（新曝露）：無 / IDENTITY_TYPE / DEPT_POSITION / GROUP_POSITION，附一行說明文字。後端 `update_role`/`create` 需將 `exclusive_group` 加入可寫欄位（**僅自訂角色**；系統角色維持 API 白名單 description/sort_order/is_active）
  - **role_level 不曝露**（維持程式控制）
  - **RBAC 權限勾選**：放「進階：API 權限」摺疊區（`<details>` 或 Alpine collapse），沿用 `GET /api/permissions/all` + `PUT /api/permissions/role-permissions`
  - 系統角色編輯時鎖定欄位 UI 呈 disabled（與 API 白名單同步）
- 刪除：沿用 `DELETE /api/roles/<code>`（系統角色不可刪；有使用人時顯示人數並提供 force 確認）
- 角色列可展開顯示持有用戶清單（沿用現有使用人數查詢；若無現成 API 則新增 `GET /api/roles/<code>/users`）

### Tab3 帳號配角色（`accounts.js` + `_tab_accounts.html`）— ORG_ADMIN 專屬，SYSTEM_ADMIN 隱藏此 tab

- 將 `backend/app/web/account_roles.py` 的查詢邏輯搬到 `GET /api/access/account-roles`（JSON、分頁、篩選：帳號類型下拉 + 關鍵字），回傳欄位同現有大表：姓名/email、帳號類型、用戶編號、部門（SOLID/DOTTED + 部門內職務）、社群參與、角色指派清單（系統角色標預設）
- 指派/撤銷：`POST /api/access/assign`、`POST /api/access/revoke`
- **互斥群組檢查抽成共用 service**：新檔 `backend/app/services/role_assignment_service.py`，將 account_roles.py 內 assign_role 的驗證（同企業、防重複含 unit 維度、exclusive_group 全域/每 unit 互斥）與 revoke 邏輯搬入；API 端點薄殼呼叫 service
- 查詢必須：排除 SYSTEM_ADMIN 帳號、`current_user.org_secure_code` 限定本企業、`is_deleted=False`（DATA-01：此頁為帳號管理場景，停用帳號仍顯示但標記狀態）

### Tab4 健檢（`health.js` + `_tab_health.html`）

- 衝突偵測：沿用 `GET /api/permissions/conflicts`（九類），列表 + 「查看」跳 Tab1 並選中該選單
- SYSTEM_ADMIN 額外按鈕：匯出 RBAC（JSON 下載）、匯入 RBAC、設定目前組態為出廠值（沿用權限中央現有 API）
- ORG_ADMIN 額外按鈕：恢復 RBAC 預設權限（沿用現有 API）
- 高風險操作（匯入、出廠值、恢復預設）一律二次確認

## 6. 後端 API 變更清單

| 動作 | 端點 | 說明 |
|---|---|---|
| 新增 | `PUT /api/menu/<sc>/permissions` | Key1 編輯 API 化（body `{"user_types": ["ORG_ADMIN", ...]}`，全量替換，呼叫既有 `MenuService.set_menu_permissions`）。`@system_admin_required` |
| 新增 | `GET /api/access/account-roles` | Tab3 資料（搬 account_roles.py 查詢）。`@admin_required` |
| 新增 | `POST /api/access/assign` / `revoke` | 薄殼呼叫 role_assignment_service。`@admin_required` |
| 新增 | `backend/app/services/role_assignment_service.py` | 互斥檢查等邏輯自 account_roles.py 搬入 |
| 修改 | `/api/roles/` create/update | `exclusive_group` 加入可寫欄位（僅自訂角色） |
| 修改（如需要） | `GET /api/permissions/menus` | 補 Tab1 需要的欄位（向下相容） |
| 沿用 | `GET/PUT /api/menu/<sc>/roles`、`/api/roles/*`、`/api/permissions/*`（all、role-permissions、conflicts、export/import、defaults） | 不動既有行為 |

新 API 檔：`backend/app/api/access_center.py`（url_prefix `/api/access`），註冊於 `backend/app/api/__init__.py`（照既有 register 模式）。

## 7. 安全規範（違反直接退件）

- 禁止硬編碼密鑰/密碼/Token；禁止 SQL 字串拼接
- API 層禁止 `Model.query` 直查 —— 透過 `ResourceGateway` 或既有 service（搬遷 account_roles 邏輯時保持其原有查詢方式即可，勿改寫成裸 query）
- 租戶隔離：所有查詢帶 `org_secure_code` 過濾（TENANT-01）；帳號查詢過濾 `is_deleted`（DATA-01）
- **禁止修改** `backend/app/security/`、`backend/app/services/page_role_guard.py`、`auth_interceptor`
- 批量套用（SYSTEM_ADMIN Key2）沿用既有 API，不自行實作跨企業迴圈

## 8. 工作包切分

| WP | 內容 | 驗收重點 |
|---|---|---|
| WP1 | 骨架：web/api blueprint、index.html + 4 個空 partial、main.js（tab 切換 + fetch/csrf helper）、CSS、migration 085（新增 access 兩筆選單 + menu_defaults） | `/access/` 可開、四 tab 可切、身分視角判斷正確 |
| WP2 | Tab1 功能授權（含 `PUT /api/menu/<sc>/permissions` 新 API） | Key1/Key2 讀寫、批量警示、header 隱藏 Key2 |
| WP3 | Tab2 角色（含 exclusive_group 後端支援） | CRUD、系統角色鎖欄位、RBAC 摺疊區、code 自動建議 |
| WP4 | Tab3 帳號配角色（含 role_assignment_service 抽取 + /api/access/*） | 大表資料、指派/撤銷、互斥檢查行為與舊頁一致 |
| WP5 | Tab4 健檢 + 全面退役（移除舊 web 路由/模板/JS、/menu/ 編輯頁鑰匙區塊瘦身、migration 086 軟刪舊選單） | 舊 URL 404/重導、新入口全功能、E2E 矩陣 |

## 9. 驗收方式（每 WP 完成後由主 Claude 執行）

- `venv/bin/python -m py_compile` 全部觸及檔案
- `sudo systemctl restart beakplatform-dev.service` 後四帳號 E2E：
  - `admin@system.local`（SYSTEM_ADMIN）、`admin-ethanyu@beluga.com`（ORG_ADMIN）：`/access/` 200 且對應 tab 功能可用
  - `ethan@lion.com`（EMPLOYEE+SECURITY_STAFF）、`er.ge.zhang.hao@lion.com`（EMPLOYEE 無角色）：`/access/` 302
- API 冒煙：quick-login + CSRF 流程（見專案 CLAUDE.md 備忘）
- i18n：新增字串跑 pybabel extract/update/補翻/compile

## 10. 後續 UI 優化規格（2026-07-17 用戶指示，尚未實作）

WP1~WP5 上線後用戶提出的兩項 UI 規格，後續優化時依此執行：

### 10.1 角色來源標記全面化

**凡 UI 上列示角色的地方，一律加標記區分「系統預設 / 企業自訂」**（依 `roles.is_system_role`）。
目的：人類在決定「能否刪除、隱藏、啟用/禁用」時一眼可判斷。

- 適用範圍：/access/ 全部四 tab（Tab1 鑰匙2 角色勾選清單、Tab2 角色列表與 modal、
  Tab3 角色指派籤與指派下拉、Tab4 衝突項的角色名），以及未來任何列角色的頁面
- 呈現建議：短徽章（如「系統」/「自訂」）或色系一致的小標籤；Tab2 列表與 Tab3 的
  「(預設)」已有雛形，需統一樣式並補齊缺漏處（尤其 Tab1 鑰匙2 清單目前完全沒有標記）

### 10.2 角色清單採 Excel 式單橫列排版

**角色項目的名稱與 code 改為左右同一列，不可上下兩行**。

- 現況問題：Tab1 鑰匙2 角色門檻清單每個角色是「代理人(一)」上、「DEPT_PROXY1」下
  的兩行卡片，角色多的企業垂直空間浪費、掃視困難
- 目標：一個角色一橫列——`[勾選框] 名稱  code  來源標記(§10.1)  scope 標籤`，
  類似 Excel 列；欄位左右排列、對齊一致
- 適用範圍：Tab1 鑰匙2 清單優先；Tab2 modal 的進階 API 權限勾選清單、其他多列
  勾選清單比照辦理
