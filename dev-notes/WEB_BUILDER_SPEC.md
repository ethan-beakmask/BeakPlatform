# Web Builder 規格文件

## 1. 模組使用權架構

### 完整授權鏈

```
合約授權 (Contract.modules_config)
    |
    v
模組 ACL (module_access_control)
    |
    v
選單可見性 (menu_service 過濾鏈)
```

### 合約授權 (Layer 0)

系統管理員透過合約設定企業可使用的模組。`Contract.modules_config` 為 JSON 陣列，如 `["nocode_builder", "form_workflow"]`。

選單過濾鏈中 `_filter_by_contract()` 負責此層。

### 模組使用權 (Layer 1)

企業管理員控制「企業內誰能使用哪個模組」。

**DB 表**: `module_access_control`

| 欄位 | 說明 |
|------|------|
| `module_code` | 模組代碼 (如 `nocode_builder`) |
| `target_type` | ROLE / DEPARTMENT / GROUP / ACCOUNT |
| `target_secure_code` | 目標的 secure_code |
| `org_secure_code` | 企業識別碼 (租戶隔離) |

**匹配邏輯**:
- ACCOUNT: `target_sc == user.secure_code`
- ROLE: 查 `UserRoleAssignment` 比對
- DEPARTMENT: 查 `UserUnitMembership` (SOLID/DOTTED)
- GROUP: 查 `UserUnitMembership` (MEMBER)

**向下相容**: 某模組在某企業沒有任何 ACL 記錄 = 不限制（所有人可用）。

**權限範圍**:
- SYSTEM_ADMIN: 不受模組 ACL 限制
- ORG_ADMIN: 不受模組 ACL 限制（需看到所有授權模組來管理）
- EMPLOYEE / EXTERNAL: 受 ACL 控制

### 選單過濾鏈完整流程

```
MenuPermission (user_type 可見性)
    |
    v
RBAC Permission (required_permission)
    |
    v
_filter_by_contract() (合約授權)
    |
    v
_filter_by_module_access() (模組使用權)
    |
    v
_build_tree() (建構樹)
```

---

## 2. 頁面生命週期

### 狀態

| 狀態 | 說明 |
|------|------|
| `draft` | 草稿，僅可透過設計器和測試預覽存取 |
| `published` | 已發布，可透過 `/p/<sc>` 上線版路由存取 |

### 路由對照表

| 用途 | URL | 權限 | status 限制 |
|------|-----|------|-------------|
| 設計器 (新) | `/nocode-builder/lab` | login_required | 無 |
| 設計器 (編輯) | `/nocode-builder/lab/<sc>` | login_required | 無 |
| 測試預覽 | `/nocode-builder/pages/<sc>` | login_required | 無 |
| **上線版** | `/p/<sc>` | login_required | **published only** |
| 子系統 Portal | `/nocode-builder/sub-systems/<sc>/portal` | login_required + 成員 | 無 |
| 子系統管理 | `/nocode-builder/sub-systems/<sc>/config` | login_required | 無 |

### 發布流程

1. 在設計器中建立/編輯頁面
2. 儲存 (POST/PUT `/api/nocode-builder/pages`)
3. 點擊「發布」 (PATCH `/api/nocode-builder/pages/<sc>/publish`)
4. 頁面 status 變為 `published`
5. `/p/<sc>` 變為可存取
6. 可透過「取消發布」 (PATCH `.../unpublish`) 回到 draft

---

## 3. 子系統權限

### 三層模型

| 層級 | 說明 | DB 來源 |
|------|------|---------|
| Layer 1: 准入 | 使用者必須是子系統所綁社群的成員 | `dc_sub_systems.community_sc` + `UserUnitMembership` |
| Layer 2: 頁面可見性 | 依角色 (admin/member) 控制哪些頁面可見 | `dc_sub_system_pages.visible_roles` |
| Layer 3: 資料控制 | 依角色控制 CRUD 權限 + 資料篩選 | `dc_sub_system_pages.role_crud_config` / `role_filters_config` |

### 變數替換

`data_filters` 中的變數在 server-side 替換：

| 變數 | 替換為 |
|------|--------|
| `$CURRENT_USER` | 當前用戶 secure_code |
| `$TODAY` | 今天日期 (YYYY-MM-DD) |
| `$CURRENT_YEAR` | 今年 (YYYY) |
| `$CURRENT_MONTH` | 本月 (MM) |

---

## 4. API 參考

### 模組使用權 API

Blueprint: `module_access_bp`, prefix `/api/module-access`

| 端點 | 方法 | 權限 | 說明 |
|------|------|------|------|
| `/targets?type=&q=` | GET | admin_required | 取得可選 target 清單 |
| `/<module_code>` | GET | admin_required | 取得模組 ACL 列表 |
| `/` | POST | admin_required | 新增 ACL |
| `/<secure_code>` | DELETE | admin_required | 軟刪除 ACL |

### Page Layout API

Blueprint: `nocode_builder_api`, prefix `/api/data-crud`

| 端點 | 方法 | 權限 | 說明 |
|------|------|------|------|
| `/pages` | GET | login_required | 列出頁面 |
| `/pages` | POST | admin_required | 建立頁面 |
| `/pages/<sc>` | GET | login_required | 取得頁面 |
| `/pages/<sc>` | PUT | admin_required | 更新頁面 |
| `/pages/<sc>` | DELETE | admin_required | 刪除頁面 |
| `/pages/<sc>/publish` | PATCH | admin_required | 發布 |
| `/pages/<sc>/unpublish` | PATCH | admin_required | 取消發布 |

### Sub System API

Blueprint: `sub_system_api`, prefix `/api/nocode-builder/sub-systems`

| 端點 | 方法 | 權限 | 說明 |
|------|------|------|------|
| `/` | GET/POST | admin_required | 子系統 CRUD |
| `/<sc>` | GET/PUT/DELETE | admin_required | 單一子系統 |
| `/<sc>/pages` | GET/POST | admin_required | 頁面配置 |
| `/<sc>/pages/<psc>` | PUT/DELETE | admin_required | 單一頁面配置 |
| `/portal/<sc>` | GET | login_required + 成員 | Portal 資料 |
| `/portal/<sc>/pages` | GET | login_required + 成員 | 可見頁面列表 |

---

## 5. 前端檔案清單

### 平台層

| 路徑 | 說明 |
|------|------|
| `backend/app/static/js/module-permissions.js` | 模組使用權 ACL 管理邏輯 |
| `backend/app/static/css/module-permissions.css` | 模組權限頁面樣式 |
| `backend/app/templates/pages/admin/module_permissions.html` | 企業管理員模組權限頁 |
| `backend/app/templates/pages/admin/module_list.html` | 系統管理員模組清單頁 |

### 模組層 (nocode_builder)

| 路徑 | 說明 |
|------|------|
| `modules/nocode_builder/static/.../js/lab-designer.js` | 佈局設計器 (含 publish/unpublish) |
| `modules/nocode_builder/static/.../js/lab-viewer.js` | 頁面檢視器 (用戶模式) |
| `modules/nocode_builder/static/.../js/page-context.js` | PageContext 共享狀態 |
| `modules/nocode_builder/static/.../js/datalist-widget.js` | 資料清單元件 |
| `modules/nocode_builder/static/.../js/sub-system-portal.js` | 子系統 Portal |
| `modules/nocode_builder/static/.../js/sub-system-list.js` | 子系統列表管理 |
| `modules/nocode_builder/static/.../js/sub-system-config.js` | 子系統配置 |
| `modules/nocode_builder/static/.../css/datalist-widget.css` | 元件 + 設計器樣式 |
| `modules/nocode_builder/templates/.../lab.html` | 設計器頁面 |
| `modules/nocode_builder/templates/.../lab_view.html` | 預覽/上線版頁面 |

### Vendor

| 路徑 | 說明 |
|------|------|
| `backend/app/static/vendor/gridstack/` | GridStack 佈局引擎 |

---

## 6. DB Migration 紀錄

| 檔案 | 說明 |
|------|------|
| `scripts/migrations/legacy/031_module_access_control.sql` | 模組使用權控制表 |
| `modules/nocode_builder/migrations/004_page_layout_status.sql` | 頁面 status 欄位 |

---

*最後更新: 2026-03-14 (data_crud → nocode_builder 正名化)*
