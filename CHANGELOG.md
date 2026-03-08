# Changelog

本專案的所有重要變更都會記錄在此檔案中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

## [Unreleased]

### Fixed
- 修正 CI pipeline 不穩定問題: Tests job 改為依賴 Security Scan 完成後執行
  - Runner capacity=1 無法真正平行，改為 Security Scan → Tests → Deploy 順序執行
  - 清理 13 個 Docker 殘留網路 (孤兒 CI 容器遺留)
- 修正 CI Security Scan 自 2/27 起持續失敗的問題 (37 次連續失敗)
  - data_crud 模組 21 條 API 路由補上 `@login_required` decorator
  - semgrep 規則補上 `@module_access_required` 的 pattern-not (規則漏列)
  - 安全性無實際漏洞 (全域 before_request 攔截器仍有效)，但違反防禦深度原則

### Removed
- 清除 12 張舊平台層表單/流程表 (form_*, workflow_*, node_* 系列)
  - 這些表自 1/23 專案初始化時已被 fw_ 前綴模組層表完全取代，ORM 不再引用
  - 備份: beakplatform_dev_20260308
  - Migration: `037_drop_legacy_tables.sql`
- 清理 `hostconfig.py` 中舊表的標籤定義與清除順序

### Added
- 用戶編號改為必填欄位，建立帳號時自動採用自動編號
- `NumberingService.sync_counter_to_used()`: 建立帳號後自動推進計數器到下一個可用編號

### Changed
- 用戶編號從選填欄位搬到必填區段 (用戶建立頁 + 員工建立表單)
- `user-create-mixin.js` getter 改為普通函數 (修正 spread 運算子不保留 getter 問題)
- 移除企業建立時自動建立「管理員專用」預設單位 (`_create_default_units`)

### Fixed
- 修正工作流迴圈場景下重複簽核防護誤擋問題
  - 原因: 重複簽核檢查僅用 `node_id` 判斷，同一節點在合法迴圈中第二次執行時被誤判為重複簽核
  - 修正: 新增 `node_queue_secure_code` 欄位，改以佇列項目為粒度判斷是否重複
  - 影響: `fw_approval_records` 表新增 `node_queue_secure_code` 欄位

### Added
- 部門設定頁面整合員工建立功能
  - [新增] 改名 [新增部門]，新增 [新增員工] 按鈕
  - 中間面板三模式: 部門詳情 / 新增部門 / 新增員工
  - 選定部門下新增員工自動歸屬該部門，未選部門則歸入「未分配員工」
  - 建立成功後 `focusNode()` 導航到目標部門
- `user-create-mixin.js`: 共用員工建立邏輯 (名稱連動/密碼/翻譯/編號)
- `_employee_create_form.html`: 嵌入式員工建立表單 partial
- `POST /api/users` 增強為完整欄位支援 (native_name, english_name, employee_id, department_code 等)
- Tree 元件新增 `focusNode(id, opts)` 方法: 展開祖先 + 捲動 + 高亮動畫
- 社群設定頁面改用零依賴 Tree 元件，取代 jQuery + jstree
  - 自訂 `group-tree` renderer: 社群圖示 + 角色標籤 + 外部廠商警示
  - 外部廠商 (EXTERNAL) 可參加社群，一般成員顯示「外」紅底白字標籤
  - 外部廠商擔任管理層時，Tree 及成員面板名字紅字警示
  - 成員排序: 團長 → 副團長 → 代理人 → 外人 → 員工
  - 右側帳號面板僅顯示 EMPLOYEE + EXTERNAL 有效帳號
- `UserUnitMembership.to_dict()` 及 `group-member-candidates` API 回傳新增 `user_type` 欄位
- 部門設定頁面組織樹改用零依賴 Tree 元件，取代 jQuery (77KB) + jstree (139KB)
  - 自訂 `dept-tree` renderer: 部門圖示 + 人員角色標籤
  - Tree 元件 vendor 檔案: `backend/app/static/vendor/tree/`
  - 全部功能重寫為獨立 `departments.js` (910 行)
- 部門設定頁面 layout 重新設計
  - 左側 Tree 500px / 中間詳情 flex-1 / 右側未分配 360px
  - 編輯部門與跨部門人員並排
  - 主管+代理人(一) 與副主管+代理人(二) 左側堆疊 (330px)，員工欄右側
  - 集團名稱顯示於 Tree 表頭 (淺藍底粉紅字)
  - 視野切換: [部門] / [員工] 按鈕

### Changed
- 用戶建立頁面 (`/users/create`) 部門選擇器改用零依賴 Tree 元件，完全移除 jQuery + jsTree 依賴
- 全系統 jQuery + jsTree 引用歸零 (vendor 檔案可安全移除)
- 部門成員/未分配員工/跨部門人員 API 改為白名單過濾，只顯示 `user_type=EMPLOYEE`
  - 排除企業管理員 (ORG_ADMIN)、外部廠商 (EXTERNAL)、系統管理員 (SYSTEM_ADMIN)
  - 影響: `GET /api/units/{id}/members`, `GET /api/units/unassigned-users`, `GET /api/users`

### Fixed
- 修正外部廠商 (EXTERNAL) 可被分配到部門並出現在部門成員列表的問題

- 稽核日誌系統: after_request hook 自動記錄操作，三級細粒度控制
  - MINIMAL: 僅認證事件 (登入/登出/密碼變更)
  - STANDARD: 認證 + 寫入操作 (POST/PUT/PATCH/DELETE)
  - VERBOSE: 所有請求 (含 GET)
  - `AuditService`: 集中式稽核服務，level 快取 (每 100 次請求重讀 DB)
  - 認證事件稽核: LOGIN / LOGIN_FAILED / LOGIN_DENIED / LOGOUT / CHANGE_PASSWORD
  - Migration: `036_audit_log_enhancement.sql` (新增 request_method / request_path / status_code 欄位)
  - API: `GET/PUT /api/system-settings/audit` 稽核等級設定
- 伺服器設定頁面新增「稽核設定」區段: 三級 radio 選擇 + 保留天數 + 各級記錄範圍說明表
- 選單管理頁面模組選單辨識: 紫底白字 (menu-module) 區分模組選單與平台選單
- 選單管理頁面底部新增底色說明對照表 (紅/藍/黑/黃/紫 五類)
- 溝通對照表: `docs/GLOSSARY.md` 選單名稱與 URL 路徑對照

### Changed
- 選單管理頁面標題欄改為 sticky，捲動時固定在頂部
- 模組選單編輯頁隱藏用戶類型勾選，顯示「權限由模組使用權控制」說明
- 模組選單儲存時跳過 MenuPermission 寫入，防止誤建權限記錄
- DevTools 清除表單流程工具: 選擇全部企業時同步清除 audit_logs 表
- CLAUDE.md 精簡: 移除 emoji、移除已完成的開發步驟、更新溝通對照表引用
- 已完成的歷史文件移至 `docs/archive/` (4 份)
- `docs/PLATFORM_MODULARIZATION_PLAN.md` 精簡為架構與模組化標準 (移除已完成步驟)

### Fixed
- 修正模組選單在選單管理頁面顯示白底的問題 (缺少 MenuPermission 導致無底色)
- 修正模組選單編輯頁可勾選用戶類型的問題 (勾選後無法取消，因驗證要求至少一個)
- 帳號刪除安全防護: 禁止刪除自己綁定的員工帳號和企業原始管理員 (API + Web 雙層)
- 帳號停用安全防護: 禁止停用自己綁定的員工帳號

### Removed
- 刪除 3 個孤兒 partial: `_departments_tree_methods.html`, `_departments_dnd_methods.html`, `_departments_crud_methods.html`

### Fixed
- 選單治理分流: MenuPermission 勾選的選單不再被合約/ACL/社群過濾覆蓋
  - 根因: Step 6 合約過濾對所有模組選單一律檢查合約，system.local 無合約導致 EMPLOYEE 看不到已勾選的選單
  - 修正: 引入 `_filter_with_bypass()` 分流器，區分 `perm_governed` (MenuPermission) 與 `module_only` (模組注入) 兩種治理來源
  - MenuPermission 治理的選單直接生效，只有純模組注入的選單才經過 Steps 6~6.7 過濾

### Changed
- 子系統選單過濾改用 DB 關聯: `_filter_by_sub_system_membership()` 從正則解析 `link_target` URL 改為透過 `DcSubSystem.menu_item_secure_code` 反查
- `SYSTEM_ORG_CODE` 集中化: 從 4 處分散定義整合至 `backend/app/constants.py` 單一來源
  - 移除: `menu_service.py`、`module_menu_service.py`、`system_settings.py`、`enterprise_data.py` 的本地定義
  - 更新: `organization_service.py`、`conglomerate_service.py`、`sys_accounts.py`、`cli.py`、`organization.py`、`email_handler.py` 改用常數匯入
- system.local 合約豁免: `_get_authorized_modules()` 對系統企業直接授權所有已安裝模組，與 `get_contract_valid_range()` 永久有效邏輯一致

### Added
- Web Builder 子系統開發申請配置流程 (A-D 全部完成)
  - `SubSystemProvisionService`: 表單審批通過後自動建立子系統+社群+選單+模組權限
  - 配置 hook 嵌入 `workflow_engine.py` 的 `complete_workflow()` 尾部
  - 觸發條件: form_name='子系統開發申請' OR form_code='FORM_WF8AEB7774_EA31'
  - 選單建立時 `is_active=false`，上線才可見
- `@module_access_required(module_code)` decorator: 路由層模組權限攔截，admin 自動放行
  - 保護 Web Builder 全部設計器路由 (7 條 web + 10 條 API)
  - Portal/頁面預覽路由不受限 (保持 @login_required + 內部成員檢查)
- 子系統選單社群成員過濾: `menu_service.py` Step 6.7 `_filter_by_sub_system_membership()`
  - 解析 `link_target` 取得子系統 SC，查社群成員身份，非成員移除選單項
  - admin 不受過濾
- 社群管理權限下放給團長 (MANAGER/DEPUTY)
  - `/admin/groups/` 從 `@admin_required` 改為 `@login_required` + 權限檢查
  - 新增 `/my-groups/` 團長入口 (別名路由)
  - `list_groups()` API: admin 看全部，團長只看管理的社群
  - cross-member CRUD (4 條 API): 加 `_is_group_leader()` 檢查
  - 新增 `/api/units/group-member-candidates`: 團長用帳號搜尋 (代替 admin-only `/api/users`)
  - 前端 `isAdmin` flag 控制 UI: 非 admin 隱藏社群 CRUD、禁用樹狀拖放重組
- Publish/Unpublish 連動選單: `project_service.py` 上線/下線同步切換 `menu_item.is_active`
- 子系統列表頁新增「設計器」按鈕 (指向 `/data-crud/studio/<sc>`)
- 進度文件: `docs/WEB_BUILDER_PROVISION_PLAN.md`

- Site Map 樹狀網站地圖: 子系統頁面管理從扁平列表改為樹狀結構
  - DB: `dc_site_map_nodes` (樹狀節點) + `dc_site_map_permissions` (節點權限白名單)，migration `005_create_site_map.sql`
  - 節點類型: folder (資料夾) / page (頁面)，page 自動連結 DcPageLayout
  - 細粒度權限: 支援 ROLE/DEPARTMENT/GROUP/ACCOUNT 白名單 (無記錄=全部可見)
  - Admin 編輯器: Wunderbaum 樹 + 屬性面板 + 權限管理 + 拖曳排序，整合至子系統配置頁 tab
  - Portal V2: 左側樹狀選單 + 右側 GridStack 動態頁面載入 (不換頁)，向下相容舊卡片模式
  - 存取控制: `X-SiteMap-Node` header 支援，DataListWidget 自動傳遞 context headers
- Lookup 企業級資料物理隔離: 企業 lookup 資料搬入企業專屬 DB (org_{id})，達到真正的物理隔離
  - `LookupOrgService`: 企業級 lookup CRUD 服務，psycopg2 raw SQL 操作 org DB
  - 懶建表機制: 首次存取自動建立 `lookup_categories` + `lookup_items` 表並 GRANT sync 角色
  - 系統級 (is_system=True) 留主庫 ORM，企業級搬入 org DB，系統級資料不暴露給企業用戶
  - API 11 個端點改造: 讀操作僅回傳企業資料，寫操作分流系統級(拒絕)/企業級(org DB)
  - Migration 034 (參考 DDL) + 035 (主庫企業級資料軟刪除清理)
- IBMM 企業專屬資料庫 (org_26) 建立與 lookup 表初始化

### Changed
- `get_categories_merged()` / `get_items_merged()` 不再包含系統級資料，企業用戶僅見自己的 lookup
- Lookup API 寫操作新增系統級衝突檢查，企業類別 code 不可與系統級重複

### Added
- Lookup Table 完整管理功能 (4 Phase 實作)
  - **Phase 1 -- API**: `backend/app/api/lookup.py` 11 個 REST 端點 (categories CRUD + items CRUD + reorder + by-code)，支援 RLS 租戶隔離
  - **Phase 2 -- 管理 UI**: `/data-crud/lookup` 頁面，左側類別列表 + 右側 Wunderbaum treegrid，支援同層/跨層拖拉排序
  - **Phase 3 -- data-crud 整合**: view-config 新增 lookup source 設定、datalist-widget label 翻譯、row-form form.io select 動態注入
  - **Phase 4 -- data-specs 整合**: field-spec-editor 新增 lookup source 選擇器與預覽、spec_generator 雙向 lookup_category_code 轉換
  - reorder API 支援完整格式 `[{secure_code, parent_code, sort_order}]`，跨層拖拉同時更新 parent_code
  - create_item API 新增重複檢查 (409 Conflict)
- Wunderbaum v0.13.0 treegrid 元件引入 (`backend/app/static/vendor/wunderbaum/`)
  - Fancytree 繼任者，零依賴，支援虛擬渲染、treegrid 多欄、拖拉排序
  - Bootstrap Icons 1.11.3 CSS 配套引入
- 前端技術棧文件化: `docs/PLATFORM_MODULARIZATION_PLAN.md` 新增技術棧段落

### Fixed
- 安全審查修正 (2026-03-02 審查範圍: 02/26~03/02)
  - **TENANT-01 違規**: `ModuleAccessService.remove_access()` 缺少 `org_secure_code` 過濾，可跨租戶刪除 ACL 記錄
  - 18 筆孤兒 MenuPermission 清理: 已刪除選單仍有活躍權限記錄
  - `org_hidden_functions` 不當對 EMPLOYEE/EXTERNAL 可見
  - `deactivate_module_menus()` / `get_module_menus()` 前綴匹配改為精確匹配 (避免誤匹配同前綴模組)
  - `_filter_by_module_access()` 移除不當的 `db.session.rollback()` (避免取消外層交易)
  - migration 032 移除不再需要的 MenuPermission 建立段落

### Added
- 模組選單動態注入: 模組選單可見性改由 `module_access_control` 驅動，不再依賴 MenuPermission 硬寫
  - SYSTEM_ADMIN / ORG_ADMIN: 自動注入所有已安裝模組選單（合約過濾仍在後續生效）
  - EMPLOYEE: 根據 `/admin/module-permissions` 的授權自動注入對應模組選單
  - 新增 `_get_all_module_menu_codes()` / `_get_module_access_menu_codes()` 方法
- Web Builder 選單定義: `032_web_builder_menus.sql` 建立 `web_builder` / `web_builder.sub_systems` / `web_builder.lab` 選單項目
- 模組使用權控制: 企業管理員可指定角色/部門/群組/帳號對模組的使用權
  - `module_access_control` 表 + `ModuleAccessControl` Model + `ModuleAccessService`
  - 選單過濾鏈新增 `_filter_by_module_access()`: 合約過濾之後插入模組使用權檢查
  - SYSTEM_ADMIN / ORG_ADMIN 不受限，EMPLOYEE / EXTERNAL 依 ACL 控制
  - 向下相容: 無 ACL 記錄的模組 = 不限制（所有人可用）
  - API: `/api/module-access` (CRUD + targets 查詢)
- 模組使用權管理 UI (`/admin/module-permissions`): 已授權模組行增加「管理使用者」按鈕
  - 展開 ACL 管理區，支援新增/移除指派，類型下拉 + 搜尋選擇對象
  - `module-permissions.js` + `module-permissions.css` 獨立靜態檔
- 系統管理員模組清單頁 (`/admin/module-list`): 展示已安裝模組及各企業授權狀態
- Web Builder 頁面狀態: `dc_page_layouts.status` 欄位 (draft/published)
  - 設計器工具列顯示狀態標籤 + 發布/取消發布按鈕
  - 發布後顯示上線版 URL `/p/<sc>`
  - API: `PATCH /api/data-crud/pages/<sc>/publish` + `/unpublish`
- 上線版頁面路由 `/p/<sc>`: 僅限 published 狀態，支援子系統 context
- Web Builder 模組登記: `web_builder` 加入 INSTALLED_MODULES (manual=True)
- 規格文件: `docs/WEB_BUILDER_SPEC.md`

### Changed
- `sync_installed_modules()` 跳過 `value.manual=True` 的項目，避免手動登記的模組被自動刪除
- 模組權限頁面無合約模組顯示「無有效合約」（原為「未授權」）
- 模組選單同步不再重建管理員已刪除的選單（`module_menu_service.py` 查詢含 is_deleted）

### Fixed
- 新建 DB 表 `module_access_control` 補 GRANT 給 beakplatform 用戶，避免 InsufficientPrivilege 錯誤
- `get_accessible_modules()` / `_filter_by_module_access()` 加 try/except + rollback 保護，避免查詢失敗汙染 session
- 修正模組選單同步重建已刪除選單的問題（form_workflow.pending / my_forms 重複）

- 合約驅動模組授權: 模組選單依企業有效合約的 modules_config 控制可見性
  - MenuService 新增合約過濾: `_get_authorized_modules()` / `_filter_by_contract()` / `_get_module_code_for_menu()`
  - SYSTEM_ADMIN 不受合約限制 (bypass)，非系統管理員依合約授權顯示模組選單
  - 模組選單判定: code 前綴匹配 INSTALLED_MODULES Lookup Table
- 模組權限管理頁面 (`/admin/module-permissions`): 列出平台已安裝模組與企業授權狀態、相關合約資訊
  - MODULE_ADMIN 角色 (module:manage 權限) 控制頁面存取
  - 模組區下新增「模組權限管理」選單項目
- 選單權限顏色系統: 依 CSV 權限顏色表完整實作 4 級 + cross
  - 系統管理員 (紅底白字/紅底黃字)、企業管理員 (藍底白字/藍底黃字)、企業員工 (黑底白字/黑底黃字)、外部廠商 (黃底黑字)
  - 固定項目 (儀表板、個人設定、表單中心、模組區) 黑底白字
  - viewer-independent 邏輯: 底色=最高權限等級，cross=有更低等級也能存取
  - base.html menubar + /menu/ 管理頁面 + menu.js sidebar 三處統一

### Changed
- 選單顏色邏輯從 viewer-dependent 改為 viewer-independent (與 /menu/ 管理頁面一致)
- `_menu_color_class()` context processor 從 8-class 映射簡化為與 CSV 對應的完整 4 級系統
- menu.css 從舊版 8-class 更新為 CSV 對應的 8+1 class (含 fixed)
- /menu/ 管理頁面 (list.html) 顏色邏輯擴展: 新增 employee/external 級別支援

- Lookup Table 通用選項清單架構
  - `lookup_categories` + `lookup_items` 兩張表，支援系統級 (org=NULL) 與企業級選項
  - RLS 政策: 一般用戶看系統級+自己企業，系統管理員看全部
  - LookupCategory / LookupItem Model (繼承 BaseModel，org nullable)
  - LookupService: CRUD + 記憶體快取 (lazy load) + 模組同步
  - 模組啟動時自動同步已安裝模組到 `INSTALLED_MODULES` category
  - 合約新增/編輯 Modal 整合授權模組多選 (來源: Lookup Table)
  - 開發速查文件 `docs/LOOKUP_TABLE_GUIDE.md` (SQL + JSONB 操作範例)
- Code 欄位自動建議: 全平台 8 個建立頁面統一支援輸入名稱自動產生代碼建議
  - 通用 Code API (`POST /api/code/generate`, `POST /api/code/validate`)，支援 8 種實體類型
  - 前端可重用元件 `code-input.js` (Alpine.js mixin) + `_code_input.html` (Jinja2 partial)
  - code 欄位改為選填，留空時後端自動產生；手動輸入即時驗證格式與唯一性
  - 重複檢查改為 case-insensitive，避免 `Admin` 和 `ADMIN` 共存
  - CLAUDE.md 新增 FRONT-04 規範

### Changed
- CodeGenerator 放寬大小寫限制: CODE_PATTERN 接受混合大小寫，自動產生的建議仍為大寫
- 所有建立邏輯移除 `.upper()` / `.toUpperCase()` 強制轉換
- 部門/社群頁面名稱欄位移至代碼欄位之前（先輸入名稱觸發建議）

### Added
- Web Builder 子系統權限架構: 三層權限模型 (准入/頁面可見性/資料層控制)
  - `dc_sub_systems` 表: 子系統綁定社群 (OrganizationalUnit GROUP)，社群成員才能進入
  - `dc_sub_system_pages` 表: 頁面可見性 (`visible_roles`)、CRUD 權限覆蓋 (`crud_overrides`)、資料篩選 (`data_filters`)
  - SubSystemService: 成員檢查、角色判定 (管理層自動 MANAGER)、可見頁面過濾、頁面權限 context
  - 子系統 Portal 頁面: 卡片式導航，依角色顯示可見頁面，顯示用戶角色標籤
  - 子系統管理 UI: 列表頁 (CRUD) + 配置頁 (基本資訊/頁面管理/角色CRUD設定/資料篩選)
  - lab_view 整合: 子系統 context 時套用 CRUD 覆蓋和資料篩選，topbar 顯示角色和返回按鈕
  - 變數替換: `$CURRENT_USER` / `$CURRENT_USER_NAME` / `$CURRENT_ORG` / `$TODAY`，用於 fixed_filters 和 data_filters
  - 子系統管理 API: 完整 CRUD + 頁面管理 + Portal API + 頁面權限 context API
  - API 權限強化: View/Page CRUD 加 `@admin_required`，Row CRUD 加子系統 context 檢查
  - 模組選單新增「子系統管理」入口
- Web Builder Lab: 頁面佈局設計器與預覽功能（GridStack 拖放 + DataListWidget 資料清單元件）
- Web Builder: PageContext 共享狀態架構，取代 WidgetBus point-to-point binding
  - Widget 獨立宣告 contextOutputs/contextInputs，不需互相指向
  - Cascading Clear: 上游切換時自動連鎖清空下游，depth 上限 10 防迴圈
  - 向下相容: 自動遷移舊版 bindings 格式為 context 格式
- 頁面佈局 CRUD API（/api/data-crud/pages）+ DcPageLayout Model
- DataListWidget: 支援搜尋、排序、分頁、動態篩選、row-select 事件
- Lab Designer: 元件設定面板內建輸出/輸入 context key 設定 UI
- layout_json schema v2: `{ version: 2, widgets: [{ ..., widget: { contextOutputs, contextInputs } }] }`
- data-crud 動態篩選 API: 支援 `filter_<column>=<value>` 查詢參數
- Spec 套用/同步時自動補建 formTitle HTML Element：若表單 schema 無 `key=formTitle` 的 htmlelement，從 data-specs 名稱自動補上
- 從獨立 Spec 建立表單時自動帶入 formTitle HTML Element

### Fixed
- Field Key 限制只能使用英文字母、數字與底線（前端即時驗證紅框提示 + 儲存阻擋 + 後端 regex 驗證，含 datagrid 子欄位）

### Added
- 表單風格主題切換功能：每張表單可獨立指定外觀風格，透過 `data-form-theme` attribute + CSS scope 實現
- 新增 `security`（正式扁平）內建主題：深灰色系、無陰影、無漸層、緊湊間距、標籤水平排列
- 表單風格管理頁面（/forms/form-themes）：主題 CRUD、CSS 線上編輯、上傳/下載、啟停用
- 表單設計器風格下拉選單：從 API 動態載入可用主題，即時預覽切換
- CSS bundle 動態端點（/api/form-workflow/form-themes/bundle.css）：集中輸出所有啟用主題的 CSS
- DB Model `FwFormTheme` + migration + seed（security 主題）

### Changed
- 表單設計器、表單中心、data_crud 的主題 CSS 改為動態載入（bundle.css 端點取代靜態 link）
- 表單中心 applyFormBackground/cleanupFormBackground 支援 `formTheme` 屬性，填表/簽核/唯讀全覆蓋
- 企業獨立資料庫管理頁面 (/organizations/databases) 重構為 master-detail 佈局
  - 資料來源改為 Organization 表（排除已刪除企業），不再依賴 FwOrgDatabase 為主源
  - 左側面板：只顯示有獨立 DB 的企業，含名稱/domain 模糊搜尋、依資料表量/容量排序
  - 右側面板：AJAX 載入 DB 統計，資料表清單支援筆數/總大小欄位排序
  - system.local 不再被排除（若有 DB 即顯示）
- 企業級 /admin/org-database 頁面重構為 master-detail 佈局 + 管理功能
  - 左側：DB 資訊 + 資料表清單（全選/反選/表名排序/筆數排序/容量排序）
  - 右上：點擊表名預覽前 100 筆資料（有 id 欄位則 DESC），加密欄位紅底標記
  - 右下：點擊行號直式顯示單筆明細，上下可拖拉調整比例
  - 多選刪除：DROP TABLE 前檢查 FwSqlFormRegistry / DcCrudView 引用，標記稽核記錄後刪除

### Fixed
- 修正欄位規格編輯器儲存後 formio_type 被重設為 textfield 的問題（Alpine.js x-model + x-for race condition：替換 fields 陣列時 _uid 全部更新導致 select 元素銷毀重建，x-model 在 option 建立前觸發）

### Added
- data-crud 視圖建立時自動補建 FwSqlFormRegistry：無 Registry 的表在建視圖時自動從 DB 結構生成 form.io schema
  - 三層策略：已有 Registry 不覆蓋 > 嘗試從已發行表單還原原始 schema > 從 DB 結構反推
  - 驗證規則推導：NOT NULL 欄位自動設 required、VARCHAR(n) 自動設 maxLength
  - 來源追蹤欄位全部 NULL 標記為自動生成，與手動/SQL Sync 建立的 Registry 區分

### Changed
- data-crud 欄位配置預設 label 改用 DB comment（若有），取代原始欄位名稱
- data-crud 無 schema 錯誤提示更新為更友善的說明

### Changed
- 欄位規格編輯器新增欄位機制重構：移除底部單列 newRow 輸入，改為 [+] 按鈕批次新增 10 列空白欄位
- 新建規格頁面預設帶 10 列空白欄位，方便直接填寫

### Fixed
- 修正欄位規格編輯器最後一列 Type 下拉選單選擇後套用到錯誤欄位的問題（blur 觸發 commitNewRow 導致 DOM 重繪）
- 修正欄位規格編輯器 Field Key 輸入框每打一個字就失去焦點的問題（x-for :key 使用 field_key 導致 Alpine 重建 DOM，改為穩定 _uid）
- 儲存規格時增加驗證：檢查 Field Key 重複、Label 缺漏，空白列自動略過

### Added
- 獨立規格套用 SQL Table 時自動建立 FwSqlFormRegistry，data_crud 可直接取得 form.io schema
- FwSqlFormRegistry 新增 `spec_secure_code` 欄位，追蹤來源規格
- registry-overview API 納入有 spec 但尚無 registry 的表單，不再遺漏未建表的規格

### Changed
- FwSqlFormRegistry 放寬 `mapping_secure_code`/`published_secure_code`/`form_template_secure_code` 為 nullable（獨立規格無此概念）
- registry-overview API 過濾孤兒 spec（指向已刪除 template），獨立規格由 standalone API 處理不重複

### Removed
- data_crud plain input fallback：移除 row_form.html/row-form.js 的 plain input 殘留，統一使用 form.io 渲染

### Fixed
- 全站內部頁面跳轉統一改為當前頁開啟，移除不必要的 _blank（data-specs、form_designer、workflow tree、sync-control）
- data-specs 頁面「表單綁定規格」區塊無 registry 項目不顯示的問題（hasVisibleRegistries 修正）
- data-specs 頁面 x-for :key 防禦 null form_template_secure_code

### Added
- data_crud 模組：無碼 CRUD 工具
  - 選表 -> 欄位配置 -> 自動產生增刪改查介面
  - 統一企業 DB 路由：所有資料操作透過 view.org_secure_code 連線企業專屬資料庫
  - 系統欄位自動識別：id/form_instance_secure_code/row_index 強制唯讀、簽核表全欄位鎖定、BYTEA(PII) 欄位保護
  - 前後端雙重保護：前端 checkbox 禁用 + 伺服器端強制拒絕系統欄位寫入
  - 完整 REST API：schema 讀取、視圖 CRUD、資料列 CRUD（含單筆查詢）
  - 分頁、搜尋、排序、軟刪除支援
  - 全頁面新增/編輯（row_form.html）取代 Modal 模式
  - form.io 整合：SQL Sync 表自動使用 form.io 渲染與驗證
  - form.io schema 查詢 API（`GET /views/<sc>/formio-schema`）
  - 新增資料時自動填入系統欄位（form_instance_secure_code 等）
- FwSqlFormRegistry 新增 `form_schema` 快取欄位：建立 registry 時從 published.form_snapshot.schema 複製，data_crud 單次查詢即可取得 schema

### Changed
- data_crud DB 連線策略：移除系統管理員直連主資料庫的路徑，統一走企業 DB pool（與 SQL Sync 一致）
- data_crud 視圖設定：系統欄位表單可見性改為用戶可控（唯讀保護不變）
- data_crud 識別符正規表達式改為支援 Unicode

### Fixed
- hostconfig 重啟按鈕修正：改用 systemd-run transient service 脫離 Flask cgroup，解決 systemctl stop 連帶殺死重啟腳本的問題
- 重啟後頁面 reload 等待時間從 5 秒改為 15 秒，配合實際重啟耗時

### Added
- Spec 編輯器新增 SQL Table 直接操作功能：設計階段即可建立/更新 org DB 表
  - 「從 SQL Table 同步」按鈕：列出 org DB 所有表，選取後匯入欄位定義到 spec
  - 「套用到 SQL Table」按鈕：將 spec 欄位定義 CREATE 或 ALTER 到 org DB，含 DDL 預覽確認
  - 表名規則：使用 form template code 或獨立 spec 自動產生碼（FT{8hex}）+ 版本號
  - 5 個新 API 端點：sql-tables, sync-from-sql-table, apply-to-sql-table（template/standalone 兩組）
- FwFormFieldSpec Model 新增 `sql_table_code` 欄位，供獨立規格產生 SQL 表名

### Fixed
- 從規格建立表單（create_form_from_spec）缺少 code 自動產生，導致表單 code 為空

### Added
- 版本歷史取回功能：載入舊版規格預覽，可「取回為新版」或「取回並套用到表單設計」
- 配對版本顯示資料表名稱欄位
- 三向比對結果顯示版本資訊（Spec 版本、表單版本、SQL 表名）
- 從規格建立表單支援選擇分類（Modal 取代 prompt）
- 資料規格三面相同步中控：Spec / FormIO(JSONB) / SQL Table 三面相 6 方向雙向同步
  - 獨立 Spec CRUD：FwFormFieldSpec 可獨立存在（不綁定表單），支援命名、版本歷史、關聯表單、從 Spec 建立表單
  - 重複版本防止：儲存時 JSON 深度比對，內容無變更時不建新版
  - SQL 結構讀取：從企業 DB `information_schema.columns` 讀取實際表結構，PG_TO_FORMIO 反向映射
  - SQL->Spec 反向同步：從企業 DB 表結構建立/更新 Spec
  - ALTER TABLE 管理：compute_alter_plan 計算變更計劃（ADD/ALTER TYPE/DROP COLUMN），風險等級評估（low/medium/high/critical），SAVEPOINT 交易安全
  - 高風險操作確認：DROP COLUMN 有資料時需輸入表名二次確認
  - 同步中控台頁面 (`/forms/data-specs/<ft_sc>/sync`)：三面相狀態卡片 + 6 方向同步按鈕 + 偏移細節
  - FormIO<->SQL 直接同步支援「同時更新 Spec」勾選（新增一版，非覆蓋）
  - FormIO vs SQL 直接比對 (`compare_formio_vs_sql`)
- 資料規格列表增加「獨立規格」區塊：列出未綁定表單的規格，支援編輯、刪除
- 資料規格列表增加「同步中控」按鈕：已有 Spec 的表單可跳轉同步中控台
- Spec 編輯器 standalone 模式：獨立規格使用 spec_sc 做 CRUD，不需 form_template_sc

### Changed
- FwFormFieldSpec/FwFormFieldSpecHistory Model：`form_template_secure_code` 改 nullable，新增 `name` 欄位

### Fixed
- 欄位規格編輯器 detailForm 初始值缺少 constraints 物件，Alpine 綁定報 TypeError
- 分類篩選統一使用 DB 真實分類 `SYS_CAT_OTHER`（其他），移除錯誤注入的虛擬 `__uncategorized__` 分類
- 選中「其他」分類時同時顯示 `category_secure_code=NULL` 的項目（表單/流程/表單中心三頁面統一）

### Added
- 企業獨立資料庫監視頁面：顯示企業 DB 用量、資料表數、每表筆數、硬碟佔用空間
  - 系統級 (`/organizations/databases`)：系統管理員可查看所有企業 DB
  - 企業級 (`/admin/org-database`)：企業管理員只看見自己的 DB
- 選單新增「企業管理」第一層分類，底下整合「企業與合約管理」及「企業獨立資料庫管理」

### Changed
- 企業列表左側面板加寬為 620px，改為分欄佈局：ID / 企業名稱 / 網域名稱 / 集團 / 合約
- 欄位規格編輯器改為 Excel-like Grid 介面：所有基本欄位（Label、Field Key、Type、PG Type、PII、Required、Description）直接在表格內 inline 編輯，取代原本逐欄開 Modal 的方式
- 欄位規格編輯器新增空白列自動新增機制：在表格底部空白列輸入 Field Key 後 blur/Enter 即自動加入欄位
- 欄位規格編輯器 FormIO Type 連動 PG Type：切換 Type 時自動帶入對應預設值，手動修改過 PG Type 後不覆寫（`_pgTypeOverridden` flag）
- 欄位規格編輯器「詳細」按鈕開啟進階設定 Modal（constraints、default_value、options、grid_children），基本欄位不再需要開 Modal
- 資料表規格管理頁面改為卡片式 Registry 分組佈局：每張表單一個獨立卡片，展開顯示發行版本清單含 SQL 表名、欄位數、筆數
- 資料表規格管理頁面新增三向比對 Modal：卡片操作列直接開啟比對結果，顯示規格 vs 表單 / 規格 vs SQL 偏移細節

### Added
- 資料表規格管理頁面：獨立選單入口 (`/forms/data-specs`)，以表單為分組主軸列出所有 SQL 同步 Registry
  - 可展開子列顯示各發行版本的 SQL 表名、欄位數、筆數、同步時間（按版本排序）
  - 操作按鈕：編輯規格（跳轉 spec editor）、建立規格（sync-from-formio）、三向比對（Modal 顯示）
  - 新增規格 Modal：選擇尚無 spec 的表單範本，跳轉建立
  - API：`registry-overview`（總覽）、`available-templates`（可選範本）

### Changed
- 三向比對結果改為明確的組別狀態顯示：規格 vs 表單（一致/有偏移）、規格 vs SQL（一致/有偏移/未建立），取代原本 `total_drifts === 0` 即顯示「三向完全一致」的不精確邏輯

### Added
- Schema-First Form Builder：欄位規格編輯器，作為表單結構的 single source of truth
  - 欄位規格 CRUD：新增/編輯/刪除/拖曳排序欄位，支援 FormIO type、PG type、constraints、PII 標記
  - FormIO 雙向轉換：從 FormIO schema 同步建立 spec (`sync-from-formio`)、從 spec 生成 FormIO schema (`generate-formio`)
  - 套用到表單：將 spec 套用至 FormIO schema (Replace 模式，保留 layout 容器)
  - 三向偏移偵測：Spec vs FormIO vs SQL 比對，偵測 type_mismatch、missing field、pii_mismatch
  - 版本歷史：每次儲存自動遞增版本號、記錄欄位快照與變更差異 (added/modified/removed)
  - SQL Sync 整合：建表時自動查詢 spec，有 spec 時優先使用 spec 定義的 pg_type 和 is_pii
  - UI 入口：表單範本列表「規格」按鈕 + 表單設計器「規格」按鈕
- 欄位規格 DB Migration (`009_field_specs.sql`)：`fw_form_field_specs` + `fw_form_field_spec_histories` 表

### Added
- 主機設定「清除標記刪除的資料」功能：永久刪除各表 `is_deleted=true` 的個別記錄，支援全系統或特定企業範圍
- 清除功能掃描/預覽：動態偵測所有含 `is_deleted` 欄位的表，顯示各表待清除筆數
- 清除功能孤兒清理：刪除 soft-deleted 父記錄前，自動清理指向它的子記錄
- 登入表單欄位偽裝與 Honeypot 機制：共用登入表單使用偽裝欄位名稱防止自動化猜測，並加入 decoy 欄位偵測機器人填寫

### Changed
- 伺服器設定頁面應用程式密碼欄位改為星號遮蔽顯示（`type="password"`）

### Security
- .gitignore 加入 Google Cloud Service Account 金鑰排除規則（`beakmask-*.json`）

### Added
- 批次匯出/匯入功能：表單模板和流程模板支援 JSON 格式批次匯出與匯入
- 流程匯出含樹系收集：匯出主流程時自動 BFS 遞迴收集所有子流程，完整保留樹系結構
- 匯入防呆機制：export_type 類型檢查（表單/流程互斥）、code 格式驗證（表單需 FT/FORM_ 開頭，流程需 WF/SF 開頭）、code 重複自動跳過
- 發行時子流程樹系快照：發行表單流程配對時自動收集並快照所有子流程 graph，存入 workflow_snapshot.sub_workflows
- SubFlowHandler 快照優先讀取：執行子流程時優先從發行快照讀取 graph，確保同一發行版本的案件使用相同版本的子流程

### Added
- 伺服器設定新增「套件版本」頁面：Python 後端套件 + 前端 vendor 套件版本與線上最新版比對
- 套件版本 API (`GET /api/system-settings/package-versions`)：並行查詢 PyPI/npm、30 分鐘快取、支援強制刷新

### Changed
- 前端 vendor 套件大版本升級 (Issue #13)：Formio 3.44.0→5.3.0、jQuery 3.7.1→4.0.0、Font Awesome 6.4.0→7.2.0
- Formio v5 適配：所有頁面加入 `Formio.icons = 'fontawesome'`（v5 預設改用 Bootstrap Icons）
- 套件版本頁面調整：前端 Vendor 套件表格移至 Python 套件表格上方
- Python 套件全面升級 (Issue #13)：21 個套件升級至最新版
  - 大版本：bcrypt 4→5, gunicorn 21→25, pytest 7→9, pytest-cov 4→7, redis 5→7, Flask-Session 0.5→0.8, cryptography 41→46, Flask-Limiter 3→4
  - 小版本：Flask 3.0→3.1, Werkzeug 3.0→3.1, itsdangerous 2.1→2.2, Flask-WTF 1.2.1→1.2.2, WTForms 3.1→3.2, SQLAlchemy 2.0.23→2.0.46, psycopg2-binary 2.9.9→2.9.11, Flask-Migrate 4.0→4.1, alembic 1.13→1.18, pytz 2023→2025, python-dateutil 2.8→2.9, requests 2.31→2.32, pypinyin 0.50→0.55
- Flask-Limiter 4.x 適配：`RATELIMIT_STORAGE_URL` 改為 `RATELIMIT_STORAGE_URI`
- Flask-Session 0.8 適配：Dev/Test session 從 `filesystem` + `SESSION_FILE_DIR` 改為 `cachelib` + `FileSystemCache`
- bcrypt 防禦性檢查：`set_password()` 密碼超過 72 bytes 拋 ValueError、`check_password()` 超長密碼直接回傳 False

### Fixed
- 修正套件版本頁面 Formio 版本無法偵測的問題（v5 版本號不在檔案前 2000 字元，改用 full_pattern 全檔掃描）
- 修正 npm 預發行版本（如 `5.3.1-refb-rc.0`）導致版本比對失敗顯示「無法檢查」的問題

### Removed
- 移除未使用的前端 vendor 套件：D3.js、D3-flextree、D3-org-chart、GridStack、alpine.min.js.bak
- 移除未使用的 Python 套件：python-dotenv、pydantic、email-validator、Flask-Cors、factory-boy、faker、bandit、safety

### Added
- 系統管理員管理企業管理員（救援功能）：查看特定企業管理員列表、啟用/停用、重設密碼
- 企業管理頁面右側面板新增「管理員管理」導航按鈕
- 預設管理員帳號安全強化：建立新管理員後自動停用預設 admin 帳號，企業管理員無法自行啟用，僅系統管理員可啟用

### Added
- 登入頁欄位偽裝：企業員工與外部廠商登入頁新增 OTP1/OTP2 decoy 欄位，真正密碼從 OTP1 讀取
- 登入頁反自動化：HTML/CSS 完全移除 password/pwd/pass 關鍵字，所有欄位改用 `type="text"` + CSS `text-security: disc` 遮蔽
- 登入頁 Honeypot 偵測：decoy 欄位被填寫時記錄 `[HONEYPOT]` warning log
- 快速登入頁新增 EXTERNAL 外部廠商 badge
- 企業列表頁新增 flash message 顯示（修復建立企業成功訊息殘留問題）

### Changed
- 快速登入頁加寬至 1100px，企業列表高度可顯示 6 筆
- 快速登入頁帳號列表改為姓名與 email 橫排對齊，移除密碼顯示
- 快速登入頁企業與帳號查詢補上 `is_active=True` 過濾

### Fixed
- 企業建立成功訊息殘留：列表頁未消費 flash message，導致下次開新增頁時顯示舊訊息

### Added
- 變數插入器 (VarPicker)：流程設計器節點配置欄位旁新增 `{x}` 按鈕，點選即可從分組清單插入 v2 語法變數
- 變數插入器：支援搜尋篩選、游標位置插入、外部點擊/Escape 關閉
- 變數插入器：自動收集表單欄位 (`f.*`)、表單實例 (`fi.*`)、流程變數 (`v.*`)、流程資訊 (`wi.*`)、節點資訊 (`n.*`)、時間 (`t.*`)
- 變數系統 v2：前綴制語法 (`${f.key}`, `${fi.applicant}`, `${v.var}`, `${wi.code}`, `${n.name}`, `${t.now}`)
- 變數系統 v2：三層 scope 架構 (TREE 跨流程 / FLOW 單流程 / NODE 單節點)
- 變數系統 v2：`fi.*` 前綴解析表單實例屬性 (applicant_name 等系統變數)
- 變數系統 v2：NODE scope 自動清理 API (`cleanup_node_vars`)
- 變數系統 v2：NODE scope 自動清理整合 — node_runner 節點完成後自動呼叫 `cleanup_node_vars()`
- 變數系統 v2：DB migration (`029_variable_system_v2.sql`)，GLOBAL→FLOW / LOCAL→NODE 遷移
- 變數系統 v2：規格文件 (`docs/VARIABLE_SYSTEM_SPEC.md`)
- 變數系統 v2：批次遷移腳本 (`scripts/migrate_variable_syntax.py`)，舊語法→v2 前綴制，支援 --dry-run
- Forgejo Issue #12: 變數系統 v2 追蹤

### Changed
- 後端 handler 統一改用 `set_flow_var()`：form_center.py、fieldread_handler、fieldwrite_handler、opset_handler
- 流程設計器所有變數語法提示表更新為 v2 前綴語法
- OpSet handler `_evaluate_value()` 改用 `replace_variables()` 統一解析，支援所有 v2 前綴
- OpSet handler `_evaluate_expression()` 支援 v2 前綴 (v./f.)
- SubFlow paramMapping 改用 TREE scope 傳遞跨流程變數（取代原 TODO）
- Branch handler `_resolve_value()` 支援 v2 前綴 (`f.`, `fi.`, `v.`)
- 變數總覽欄位標題：「舊式變數」→「內部變數」、「新式變數」→「引用語法」
- VariableService 全面重構：新增 tree/flow/node 三層 API，保留舊別名向下相容
- BaseNodeHandler `replace_variables()` 重寫為前綴分派機制，保留 legacy fallback

### Added
- FormAdapter 設定 Modal 對話窗：節點設定從右側面板搬入 960px 寬獨立 Modal，雙欄佈局（左：簽核設定，右：決策控制器）
- 右側面板 FormAdapter 摘要卡片：精簡顯示簽核者、模式、備註、決策狀態，一鍵打開設定
- 通用 Accordion 手風琴元件（`.bk-accordion-*` CSS），可用於未來其他節點設定面板
- FormAdapter 設定 Modal 三頁籤版面：基本設定 / 決策控制器 / 欄位權限設定
- 欄位權限設定內嵌於 Modal Tab 2，切換頁籤時自動載入，儲存時一併寫入 node config
- 決策項目共用組態方塊：多個決策選項共用一個編輯面板，點選連連看左方項目切換內容
- 連連看 (Edge Mapping) UI：決策選項 ↔ 出線去向 N:M 配對，SVG 即時連線
- 變數總覽分頁：掃描所有節點類型的變數（OpSet/FormAdapter/SqlExecutor/Branch/Subflow/Telegram/Email/OpFieldWrite），支援 SET/READ 分類篩選

### Changed
- FormAdapter 設定 Modal 改為全螢幕高度，不隨內容變化大小
- OPSET 變數分頁擴充為「變數總覽」，表格新增分類(SET/READ)、節點類型欄位
- 決策控制器版面調整：連連看移至上方、決策設定移至下方、移除提示佔位框
- 已啟用自定義決策時，開啟 FormAdapter Modal 直接跳到決策控制器頁籤
- FormAdapter 套用設定時同步更新變數總覽
- 自定義決策按鈕文字改為靠左對齊

### Fixed
- 簽核決策按鈕高亮錯誤：多個決策選項 value 相同時，點選一個全部填滿顏色，改用 option.id 判斷選中狀態
- 連連看 SVG 連線在 Tab 隱藏狀態下繪製座標為零，切換至決策控制器頁籤時自動重繪

### Added
- FormAdapter 自定義決策控制器：可自訂決策選項名稱、值、按鈕風格，取代固定的 edge label
- FormAdapter N:M 決策映射：一個決策選項可觸發多條 edge，多個選項可指向同一 edge
- FormAdapter 傳出變數（output_variable）：決策值寫入全域變數，供下游 Branch 判斷
- FormAdapter 來向變數控制（input_variables）：根據上游變數動態隱藏決策選項、調整欄位權限
- 工作流程設計器：FormAdapter 決策控制器設定面板（決策選項 CRUD、edge 映射、變數設定）

### Fixed
- Branch `_resolve_value()` 非 `form.*` 變數直接回傳空字串，未查詢 workflow 全域變數
- `advance_to_next_nodes()` 將 Branch result dict 直接傳入 `advance_workflow()`，導致 `selected_edges` 從未被使用
- 工作流程設計器：替換節點後 edge 樣式（curve-style、顏色、寬度等）全部重置為預設直線
- 工作流程設計器：Ctrl+Z 後正交折線控制點 Maps 未重建，導致正交線變直線且無法刪除
- 工作流程設計器：儲存/重載後正交折線遺失，殘留孤兒控制點（saveWorkflow 漏存 orthogonalControl 標記）
- 工作流程設計器：正交折線控制點缺少 CSS selector，bypass styles 遺失後退化成橙色小點
- 工作流程設計器：刪除節點後正交折線 relay 節點和中間段殘留（Cytoscape 只移除直接連接的邊）

### Changed
- 簽核模態框「表單內容」「請選擇決策」「請選擇後續動作」字體統一為 16px/600，與「簽核意見」一致
- 簽核模態框倒數計時從靠右改為置中顯示
- 表單中心自動刷新改用 setTimeout 鏈式排程 + 指數退避（5s→60s），分頁隱藏時暫停輪詢
- 表單中心子分類頁籤從獨立列移入 section header，與標題同列顯示

### Removed
- 表單中心「重新載入」按鈕（已有自動刷新機制，手動按鈕多餘）

### Added
- 簽核並行防護：簽核鎖定機制（`locked_by`/`locked_at`），防止多人同時簽核同一張表單
- 簽核鎖定 API：`POST/DELETE /api/form-center/pending-tasks/{id}/lock`
- 待簽核列表新增「閱讀」按鈕（眼睛圖示），可唯讀查看表單內容，不取鎖
- 簽核 Modal 倒數計時顯示（10 分鐘），逾時自動關閉表單並釋放鎖
- 關閉分頁 / 瀏覽器時自動釋放簽核鎖（best-effort `beforeunload`）

### Changed
- 簽核 API 加入 `SELECT ... FOR UPDATE` 悲觀鎖 + 鎖定持有者驗證
- 簽核 API 加入 P1 重複簽核防護（同人同節點不可重複簽核，回傳 409）
- 待簽核列表：他人鎖定中的表單顯示「簽核中」並 disabled 按鈕
- 簽核意見與倒數計時字體放大至 16px（與標題一致）

### Added
- 表單中心：管理員可批量刪除自己的測試表單（歷史區「刪除測試表單」按鈕）
- 配對管理：封存區新增「刪除」按鈕，可刪除已封存的配對
- 配對管理：發行版停用/恢復/封存/刪除時同步更新配對的 `is_published` 旗標

### Changed
- 表單中心所有表格改用 `table-layout: fixed`，欄位寬度不再被內容擠壓
- 表單中心主旨欄改用 JS 截斷（超過 56 字顯示 `[...]`），hover 顯示完整文字

### Added
- 表單設計器元件名稱中英對照：左側面板顯示「中文名(English Name)」雙語格式
- 表單主旨欄位：平台層必填欄位，獨立於 form.io schema，儲存在 `fw_form_instances.subject`
- 填寫表單 Modal 頂部新增主旨輸入框，寬度跟隨表單設計寬度
- 簽核 Modal / 閱讀表單 Modal header 顯示主旨

### Changed
- 表單中心列表（待簽核/追蹤中/歷史）主旨欄改讀 DB 欄位，移除舊版 `extract_form_subject()` 遞迴 schema 萃取
- 新建表單模板預設 schema 不再包含 `formSubject` 元件
- 表單設計器「提示→標籤」checkbox 預設啟用
- 填寫/簽核/閱讀三個 Modal 高度放大至 100vh

### Removed
- 移除表單設計器自訂「表單標題」元件（formTitle），改用標準 HTML Element 元件

### Fixed
- 修復表單/流程「另存新版」API：原本只修改版本號未建新記錄，改為複製建立新記錄
- 修復流程「另存新版」回應格式：data 未包在 `data` key 導致前端 `result.data.version` 報錯
- 修復三個 Modal 的 `formWidth` 判斷，`undefined` 時不再產生 NaN

### Added
- SQL Sync Phase 3: 簽核記錄子表 (`_approvals`)，固定 schema 同步 `FwApprovalRecord` 到企業 DB
- SQL Sync Phase 3: 既有 registry approval 子表補建工具 (`scripts/upgrade_approval_tables.py`)
- SQL Sync Phase 3: 企業 DB 密碼自動輪換腳本 (`scripts/rotate_credentials.py`)，支援 `--dry-run`/`--force`/`--max-age`
- SQL Sync Phase 3: Systemd Timer 定時輪換排程（每週日凌晨 3:00，90 天閾值）

### Fixed
- SQL Sync 同步表動態欄位一律改為 NULLABLE，避免表單空值導致同步失敗（required 是 UI 驗證，非 DB 約束）
- SQL Sync `column_mapping` 遍歷跳過 `_` 前綴保留 metadata key，修復 `_approval_table` 字串值被當 dict 存取的錯誤

### Added
- SQL Sync Phase 2: Datagrid/Editgrid 明細子表 (`_items_{grid_key}`)，將 JSONB 陣列展開為獨立 rows
- SQL Sync Phase 2: PII 欄位加密（pgcrypto `pgp_sym_encrypt`），標記為 PII 的欄位在 org DB 中以 BYTEA 加密儲存
- SQL Sync Phase 2: 舊資料回補工具 (`scripts/backfill_sync.py`)，批次補寫入已終態的歷史表單
- SQL Sync Phase 2: 既有 registry 子表補建函式 (`upgrade_registry_sub_tables`)
- SQL Sync 架構重構：每個企業使用獨立 PostgreSQL 資料庫 (org_{id})，雙權限帳號分離 (bfadmin/bfsync)
- SQL Sync Background Worker daemon (systemd service)，佇列式非同步同步取代同步 UPSERT
- SQL Sync 加密憑證儲存 (Fernet)，支援密碼輪換
- SQL Sync 架構文件 (`docs/SQL_SYNC.md`)
- 配對封存機制：所有發行版本都已封存時，可將整個配對歸檔，從主清單移至封存清單
- 封存清單區塊：可收合展示區，顯示封存計數、封存時間，支援「恢復」操作回到主清單
- 發行版本刪除：未被使用過且非運作中的發行版本可刪除（版本 Modal 內操作）

### Changed
- 配對列表「發行名稱」欄位移至第一欄
- 配對列表「發行」「重新發行」按鈕統一改名為「新發行」
- SQL Sync 改為流程結束時同步（終態資料），移除送出/簽核時的同步觸發
- SQL Sync 開關改為單向啟用（必須已發行，啟用後不可關閉）
- SQL Sync sync 帳號權限擴展為 SELECT/INSERT/UPDATE/DELETE（子表同步需要 DELETE）
- SQL Sync 企業 DB 建立時自動安裝 pgcrypto extension
- restart_flask.sh 加入 Sync Worker 重啟
- SQL Sync 表結構精簡：固定欄位只保留 form_instance_secure_code，系統欄位由主庫提供
- SQL Sync 表命名簡化為 form_{mapping_id}_v{version}
- 樹系圖與未用子流程合併為分頁介面：點擊 [樹系圖] 或列表 [未用] badge 開啟同一視圖，兩個頁籤懶載入切換
- 未用子流程頁籤新增「刪除行為參考」表格（置頂，縮圖卡片在下）
- 表單中心歷史表單新增「結束時間」欄位（位於狀態與流程耗時之間）
- 表單中心三個 tab 可排序表頭：點擊「單號」、「等待時間」、「送單時間」、「結束時間」切換正/逆排序（伺服器端排序）
- 排序指示符：未排序欄位顯示 ⇅，正排序顯示 ▲，逆排序顯示 ▼
- Abandon（中止）節點 handler 及流程設計器配置面板
- 節點定義 label 顯示 node type（方便開發辨識）
- 未用子流程面板「全部刪除」按鈕：一鍵刪除所有未使用的專屬子流程
- 流程設計器流程樹系面板新增「樹系圖」按鈕（樹木圖示），在新分頁開啟縮放式樹系圖
- 空群組自動顯示虛線邊框：群組內所有節點被移出後，強制顯示虛線邊框並保持原有顏色，避免空群組在畫布上消失不見
- 節點框選視覺回饋：選中節點顯示藍色邊框 + 陰影光暈（border + shadow），方便辨識已選取的節點
- 流程列表「未用」數字可點擊：開啟未使用專屬子流程面板，顯示縮圖卡片（5 欄 grid），支援編輯與刪除
- 未用子流程 API (`GET /api/form-workflow/workflows/<secure_code>/unused-subflows`)：回傳未被 graph 引用的專屬子流程含縮圖
- 流程樹系圖增加未引用子流程：tree API 自動附加 `is_unused` 標記的未使用專屬子流程
- 通用子流程唯讀模式：從流程樹切換到通用子流程時自動啟用唯讀（禁用儲存、鎖定拖動、禁用節點面板拖入、右側設定面板變淺色不可操作、顯示提示條），僅從流程管理頁面開啟時可編輯
- 表單設計器左側面板新增「表單標題」元件（HTML Element h3 置中），拖入即用
- 新建表單模板/流程連帶表單自動帶入標題元件，content 為表單名稱
- 新增表單與新增流程的預設分類改為「流程記錄」
- 表單填寫端載入 `formio-theme.css`，實現與設計器 WYSIWYG 視覺同步
- 填寫/簽核/閱讀 Modal 灰色畫布背景 + 白色表單區域 + 陰影（匹配設計器 preview）
- 子流程刪除 API (`DELETE /api/workflows/data/subflows/<secure_code>`)：僅限專屬子流程，引用中回 409，遞迴軟刪除下層

### Changed
- 表單唯讀渲染統一為共用方法 `_renderFormReadOnly()`，三處（監控表單內容、閱讀表單、簽核表單唯讀）全部改用 `viewAsHtml: false`，修復閱讀表單/簽核表單無欄位框框的問題
- 監控模態框「表單內容」頁籤改為 block 排版（移除雙欄 flex），表單寬度正確依 formWidth 限制
- 表單中心 my-forms API limit 預設值從 50 改為 500（排序需涵蓋全部單）
- 流程設計器縮圖儲存改用 Promise 包裝確保 saveAndClose 等待上傳完成
- Abandon 節點圖示改為紅色斜線
- 樹系圖新增縮放/平移功能：上方工具列三按鈕（縮小、適應畫面、放大）+ 滑鼠拖拉平移 + 滾輪縮放，取代捲軸操作（列表頁內嵌 + 獨立頁皆支援）
- 樹系圖工具列精簡：移除流程名稱/代碼文字說明，僅保留返回按鈕與縮放控制
- 獨立樹系圖頁「關閉」按鈕改為「返回列表」（導向 `/forms/workflows`），修復 `window.close()` 無法關閉非腳本開啟頁面的問題
- 流程樹系圖改為縮圖卡片式 tree 結構：每層往右退縮、連線從卡片下緣中間出發，移除 d3-org-chart 依賴（列表頁內嵌 + 獨立樹系圖頁皆更新）
- 群組管理按鈕（建立/解散）等寬等高，各佔 50% 寬度
- 流程列表名稱欄寬度縮減至 225px、描述欄限制 200px、更新時間欄加寬至 155px

### Fixed
- 修復 datagrid/editgrid 元件同步錯誤：改為整個存為 JSONB 欄位，不再遞迴拆分子元件為獨立欄位
- 修復拖放新節點到畫布後右側設定面板未自動切換：新節點放下後立即選取並顯示該節點的設定面板
- 流程設計器流程樹系面板移除重複的主流程名稱顯示
- 修復樹系圖開啟時頁首區塊未隱藏：Bootstrap `d-flex` 的 `!important` 覆蓋 Alpine.js `x-show`，改用外層包裹 div 解決
- 修復未用子流程計數不一致（樹系圖與列表數字不同）：從全域 flat set 改為 per-workflow BFS 可達性分析，避免跨樹引用導致計數錯誤
- 修復「未用子流程」判定只看直接父流程：改為遞迴掃描整棵樹所有層級的 graph，被任何層級引用即算「已用」
- 修復通用子流程切回一般流程時唯讀狀態殘留：unlockInterface 完整清除 disabled 屬性、CSS class 和 inline style
- 修復群組管理面板修改群組名稱不生效的問題（autoApplyCurrentPanel 用右側面板舊值覆蓋）
- 修復群組名稱 blur 時因群組已取消選取導致更新失敗的競態條件
- 群組節點標籤改為頂部顯示、加粗、text-max-width 從 80 提升到 200，長名稱不再被截斷

### Changed
- SubFlow 節點配置面板重新設計：從單一下拉選單改為分區面板（專屬區含引用狀態 + 刪除按鈕、通用區按分類分組）
- SubFlow 節點依子流程類型變色：專屬綠色 (#64aa89)、通用藍色 (#6196ea)
- 通用子流程分類改為透過 `category_secure_code` 查 FwCategory 表，支援二層分類顯示
- 新拖入節點 type 經 `normalizeNodeType` 統一，修正 SubFlow 大小寫不一致導致樣式不生效
- 流程樹系名稱字體放大 (13px)
- 切換流程時自動重置節點設定面板至未選取狀態
- 工作流列表新增「未用」欄位顯示未被引用的專屬子流程數量
- 表單中心表單網格改為自適應排列 (`auto-fill, 240px`)
- 平台 navbar/menubar CSS class 改名 `.navbar` → `.bk-navbar`、`.menubar` → `.bk-menubar`，避免與 Bootstrap 衝突（影響 base.html、menu.html、menu.css、themes.css）
- `.bk-navbar` / `.bk-menubar` 明確設定 font-family/font-size/line-height，防止 Bootstrap body reset 覆蓋
- 前端 HTML 瘦身 Phase 0-3：大型模板抽離內嵌 JS/CSS 為獨立靜態檔，符合 FRONT-01/02 規範
  - Phase 0: 建立 `common.css` 共用樣式、關閉 Bulma Issue #11
  - Phase 1: `template_list.html` (700→244)、`workflow_list.html` (674→296)
  - Phase 2: `holidays.html` (1011→205)、`schedules.html` (905→226)、`form_center.html` (1880→393)、`form_designer.html` (479+1459→133)
  - Phase 3: `groups.html` (1305→238)、`users/create.html` (930→256)、`departments.html` CSS partial→靜態檔
  - Phase 4: 8 個模板抽離 — `users/edit.html` (600→361)、`mappings_list.html` (623→276)、`quick_login.html` (709→215)、`settings.html` (640→319)、`users/view.html` (497→220)、`numbering/edit.html` (451→290)、`org-admins/list.html` (391→162)、`category_list.html` (379→164)
  - Phase 5: 全模板合規審計完成，CSS 去重（移除 app.css / user-form.css 中 common.css 重複定義）
  - Phase 6: `organizations/list.html` (1004→309)、`workflow_designer.html` (1081→845，獨立頁面)
  - Phase 7: `menu.html` (406→45)、`hostconfig/index.html` (295→111)
  - Phase 8: CSS 去重 — 模態框/密碼重設/password-field/form-hint/alert/help-text 抽至 `common.css`，6 個 CSS 檔移除重複
  - Priority 3: 18 個模板 CSS+JS 抽離（含 4 個 partial 轉靜態檔），建立 `password-form.js` 共用密碼元件整合 6 處重複
- 部門/社群頁面共用 `org-tree.css` (467 行)，消除 CSS 重複
- CLAUDE.md FRONT-01 新增 JS 抽離三種模式說明 (A: 直接搬移 / B: Window Bridge / C: 保留 Partial)
- 表單設計器工具列「表單檔名」欄位寬度 180→210px、「分類」欄位寬度 140→170px
- 工作流列表新增「專屬」「通用」子流程數量欄位，API 批次計算
- 流程設計器描述欄位改為多行編輯 Modal，支援換行儲存
- 新建流程自動適應視圖，預設 Start/End 節點進入視野
- CSS 框架統一為 Bootstrap 5.3.2，移除 Bulma（`form_center.html`、`workflow_list.html`、`workflow_designer.html`）
- 刪除 `bulma.min.css`，消除 Bulma 與 Bootstrap/Form.io 的 CSS 衝突（heading 大小、columns 佈局、input 樣式）
- 工作流列表頁 Bulma → Bootstrap 改寫（表格、按鈕、標籤、Tab、Modal）
- 表單中心主旨欄位超長文字自動截斷顯示 `...`（純視覺，不影響資料）
- 刪除主流程時遞迴軟刪除所有專屬子流程及相關配對，通用子流程保留
- 刪除前檢查運行中實例，有則阻擋刪除
- SubFlow 子流程功能：引擎核心支援子流程呼叫
- 流程樹系圖獨立分頁 (`/forms/workflows/<id>/tree`)，橫向佈局含原尺寸縮圖
- 單一流程樹 API (`GET /api/form-workflow/workflows/flow-trees/<secure_code>`)
- SubFlow 節點建立/選擇子流程後自動套用並重整流程樹系
- 儲存並關閉依來源返回：從樹系圖來的回樹系圖，從清單來的回清單
- 流程監控模態框標題列顯示五欄版本資訊（發行版本、表單名稱、表單版本、流程名稱、流程版本）
- 強制結束流程功能（發起人/企業管理員可在監控畫面強制取消 RUNNING 流程）
- 歷史列表納入 CANCELLED 和 REJECTED 狀態的表單
- Docker 化 CI/CD 部署環境 (PostgreSQL 16 + Redis 7 + Gunicorn + Nginx)
- CI 通過後自動部署到 staging 環境 (192.168.0.15:8000)
- CI/CD 環境建置文件 (`docs/CICD_SETUP.md`)
- 群組功能優化：空群組修正、自訂顏色、管理面板重構
- 流程設計器所需的企業資料查詢 API
- 配對列表顯示發行版本資訊（運作版本、發行名稱、快照名稱）
- 列表多選批次操作與配對資訊顯示
- Ctrl+Z Undo 系統，替換節點改為記憶體保留
- 流程設計器快捷鍵與畫布改善
- End 節點三種結束模式 (detach/cancel/strict)
- 表單中心序號 TEST/PROC 標記補齊與獨立清單頁面
- 分類結構改為靈活一/二層（不強制子分類）
- 表單流程分類改為二層結構 (parent/child)
- 帳號管理重構與 Navbar 個人化顯示
- i18n 系統全面建置 (Flask-Babel 整合)
- 選單多語系、企業語系/時區設定、個人時區
- CI/CD 安全檢查 (Semgrep + Bandit)
- E-MailRelay 通知節點 handler
- 模組靜態檔案機制
- 表單閱讀功能與統一底圖/寬度渲染
- 分類管理與底圖管理功能
- 表單流程模組完整移轉 (Step 3)
- 安裝文件與腳本 (Step 4)
- 模組化標準驗證 (Step 5)

### Changed
- 流程設計器上方工具列改為白底扁平風格（移除漸層背景），按鈕色值對齊 Bootstrap 色系
- 流程設計器版本字體放大（11px → 14px），描述欄改為 readonly 預覽第一行
- 工作流列表移除「類型」「節點數」欄位，預設顯示模式改為清單
- 工作流列表描述欄只顯示第一行，超過 500px 自動截斷
- 縮圖生成移除多餘的 `cy.fit()`，使用 `full: true` 直接導出避免改變畫布比例
- 表單中心欄寬統一：單號 140px、表單 145px、類別 85px、發起人 90px、時間類欄位 150px
- 表單中心字體統一：內文 13px、標題/表單名稱 14px bold
- 待簽核表格欄位順序調整（單號→表單→主旨→發起人→類別→目前關卡→等待時間→操作）
- 新增工作流對話框「設為子流程」改為「設為通用子流程」，移除多餘說明文字
- 新增表單模板按鈕與對話框文字修正
- 表單/工作流對話框 checkbox 排版修正（靠左對齊）
- 流程縮圖改為單一 600×400 (3:2 橫式)，移除 1x1/1x2 兩種尺寸節省算力
- 流程縮圖生成加入 24px 白邊，cy.fit padding 縮小讓節點更大
- 表單縮圖改為 600×900 (2:3 直式)，viewport 800×800 確保並排欄位正確渲染
- 表單縮圖生成加入 PIL 自動裁切空白
- 流程列表頁/表單列表頁容器寬度從 1200px 加大至 1800px
- 流程縮圖 grid 改為 5 欄，框以 aspect-ratio 3:2 自適應
- 表單縮圖 grid 改為 8 欄，框以 aspect-ratio 2:3 自適應
- 流程樹系圖節點放大至 240×195，縮圖區 224×150
- 表單列表頁分類篩選移除「全部」chip，預設選第一個分類，無分類歸入「其他」
- 表單中心左側分類移除「全部」，預設選第一個父分類，無分類歸入「其他」
- 表單中心子分類頁籤移除「全部」，追加「其他」收納未歸子分類的表單，預設選第一個
- 工作流列表頁 Tab 精簡為「主流程」與「通用子流程」，移除全部 Tab
- 專屬子流程從列表頁隱藏，改為透過主流程的樹系圖查看
- 分類篩選移除「全部」chip，預設選第一個分類，無分類歸入「其他」
- 列表 badge 三態顯示：主流程 / 通用子流程 / 專屬子流程
- API `flow_type=subflow` 改為只回傳通用子流程（排除專屬）
- restart_flask.sh 改為確認 executor/emailrelay 服務運行，移除舊的 disable 邏輯
- ProductionConfig SESSION_REDIS 改用 redis.from_url() 建立連線物件
- CI workflow 升級為 CI/CD pipeline
- E-MailRelay 從系統安裝改為自包含安裝 /opt/E-MailRelay
- 表單設計器與流程設計器 navbar 改為共用風格
- HTML 模板瘦身：4 個大檔拆為 Jinja2 partial
- Node Type 定義改為 DB 驅動，消除 API 硬編碼
- 表單中心瘦身與全專案 port/命名修正
- 代碼內品牌引用恢復為 BeakMask

### Fixed
- 描述編輯 Modal 儲存後換行遺失（input type=text 會吃換行，改用 currentWorkflow 物件直接存取）
- 儲存流程時縮圖生成觸發 cy.fit() 導致畫布比例跳掉
- 專屬子流程被歸類為通用的 bug（to_dict 補回 parent_workflow_secure_code）
- 分類 chip 重複「其他」問題（DB 已有時不再追加）
- 工作流引擎統一使用發行快照 (graph_snapshot) 而非設計圖，避免版本間節點 ID 不匹配導致流程中斷
- CD deploy 改用直接 SSH 取代 appleboy/ssh-action (data.forgejo.org 無此 mirror)
- Docker entrypoint 表名檢查錯誤 (`user` → `organizations`)，導致重複建立 system.local
- Docker 部署缺少平台級選單初始化 (init_menus.py)
- 修復工作流節點重複執行的 race condition
- 修復 VariableService 並行寫入變數的 race condition
- 儲存流程前自動套用當前面板設定，避免 config 遺失
- E-MailRelay 服務名稱修正與流程設計器線條屬性儲存
- 通知節點 handler 群組解析修正
- 流程首次儲存自動建立表單時觸發背景縮圖生成
- 節點邊框隱藏時 Shift 連線高亮不顯示
- End 節點依結束模式變色失效修正
- Node Type 命名正規化 (方案 C Phase 1-4)
- 分類預設值修正、移除未分類選項
- 分類管理頁面空白修正
- 表單中心時區換算與 ResourceGateway 多欄位排序

## [0.2.0-pre-a6] - 2025-12-26

### Added
- Step 2 完成：權限接口、選單整合、CLI 命令
- 模組化基礎架構建立
- 用戶密碼欄位高強度密碼產生器

### Fixed
- 用戶重設密碼對話框開啟時自動產生密碼
- 企業管理員設定頁面調整

## [0.1.0] - 2025-12-20

- 初始版本：多租戶權限管理平台基礎架構
