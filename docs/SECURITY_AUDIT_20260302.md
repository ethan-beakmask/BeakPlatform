# 安全審查報告 -- 2026-03-02

## 審查範圍

- **時間**: 2026/02/26 00:00 ~ 2026/03/02 02:00
- **觸發原因**: 模組使用權 + 選單權限開發過程中多次失敗與修改，需確認無殘留安全影響
- **涵蓋 commit 數**: 30 筆
- **DB 備份**: `/opt/tmp/beakplatform_dev_backup_20260302_audit.sql` (2.1M)

---

## 發現與修正

### [嚴重] SEC-01: TENANT-01 違規 -- remove_access 缺少租戶隔離

**位置**: `backend/app/services/module_access_service.py:remove_access()`

**問題**: `remove_access(secure_code)` 僅以 `secure_code` 查詢，未驗證 `org_secure_code`。A 企業管理員若猜到 secure_code，可刪除 B 企業的模組使用權 ACL 記錄。

**影響**: 跨租戶資料操作 (TENANT-01 違規)

**修正**:
- `ModuleAccessService.remove_access()` 新增 `org_secure_code` 參數，查詢條件加入企業隔離
- `module_access.py:remove_access` API 傳入 `current_user.org_secure_code`

**狀態**: 已修正

---

### [中] SEC-02: 18 筆孤兒 MenuPermission

**位置**: `menu_permissions` 表

**問題**: 8 個已 soft-delete 的 menu_items 仍有 18 筆活躍的 MenuPermission 記錄:

| menu_item code | 數量 |
|---|---|
| form_workflow.my_forms | 4 (全部 user_type) |
| form_workflow.pending | 4 (全部 user_type) |
| test | 2 (SYSTEM_ADMIN, ORG_ADMIN) |
| time_config | 2 (SYSTEM_ADMIN, ORG_ADMIN) |
| group_list | 2 (ORG_ADMIN, EMPLOYEE) |
| approval_categories | 1 (ORG_ADMIN) |
| contracts | 1 (SYSTEM_ADMIN) |
| customer_mgmt | 1 (SYSTEM_ADMIN) |
| organizations | 1 (SYSTEM_ADMIN) |

**影響**: 無功能影響 (主查詢 `get_user_menu_tree` 的 Step 3 過濾 `is_deleted=false`)，但 `_get_allowed_menu_codes` 會將這些 secure_code 加入集合，增加無謂的查詢範圍。

**修正**: 批次 soft-delete 這 18 筆記錄。Migration: `033_security_audit_cleanup.sql`

**狀態**: 已修正

---

### [中] SEC-03: org_hidden_functions 選單可見性不當

**位置**: `menu_items` code=`org_hidden_functions`

**問題**: 此 header (標題: 暫時隱藏功能) 有 EMPLOYEE 和 EXTERNAL 的 MenuPermission，但其子項幾乎全部已刪除 (test, form_workflow.my_forms, form_workflow.pending, time_config 皆 is_deleted=true)，僅剩 sample_module 一個 active 子項（sample_module 已於後續清理中移除）。EMPLOYEE/EXTERNAL 會看到一個標題不明的空分區。

**修正**: soft-delete EMPLOYEE/EXTERNAL 的 MenuPermission。此 header 在管理員視角仍可見 (但 SYSTEM_ADMIN/ORG_ADMIN 也沒有 MenuPermission，所以實際上也看不到，除非未來補建)。

**狀態**: 已修正

---

### [低] SEC-04: deactivate_module_menus 前綴匹配不精確

**位置**: `backend/app/services/module_menu_service.py:deactivate_module_menus()`

**問題**: 使用 `MenuItem.code.like(f"{module_name}%")` 可能誤匹配同前綴模組。例如停用 `nocode` 模組會連帶停用 `nocode_builder` 的選單。

**同一問題**: `get_module_menus()` 方法也有相同的 like 匹配問題。

**修正**: 改為 `or_(MenuItem.code == module_name, MenuItem.code.like(f"{module_name}.%"))`，精確匹配模組名或以 `.` 分隔的子選單。

**狀態**: 已修正

---

### [低] SEC-05: _filter_by_module_access 中的 db.session.rollback()

**位置**: `backend/app/services/menu_service.py:_filter_by_module_access()` (line ~865)

**問題**: 在異常處理中呼叫 `db.session.rollback()`，但此方法在 `get_user_menu_tree` 的大交易中被呼叫。Rollback 會取消外層所有未 commit 的操作。

**修正**: 移除 `db.session.rollback()`，只 log warning 並 fallback 到不過濾。

**狀態**: 已修正

---

### [低] SEC-06: migration 032 建立不再需要的 MenuPermission

**位置**: `scripts/migrations/032_web_builder_menus.sql`

**問題**: Migration 的 Step 4 建立 web_builder 的 MenuPermission (9 筆)，但當前架構已改為動態注入 (menu_service.py Step 1.5)。這些記錄在開發期間被手動移除，但 fresh install 會重新建立。

**修正**: 將 Step 4 的 INSERT 語句替換為註解說明，指向新架構。

**狀態**: 已修正

---

## 無問題確認

### menu_service.py 過濾鏈完整性

> **2026-03-07 更新**: 過濾鏈架構已重構為「治理分流」模式。

7 步過濾流程 + 治理分流：
1. **Step 1** `_get_allowed_menu_codes`: MenuPermission 取得基礎可見集合 → `perm_governed_codes`
2. **Step 1.5** 模組選單注入: SYSTEM_ADMIN/ORG_ADMIN 注入全部，EMPLOYEE/EXTERNAL 按 ACL → `module_injected_codes`
3. **治理分流**: `module_only_codes = module_injected_codes - perm_governed_codes`
   - `perm_governed_codes`: 管理員在 /menu/ 勾選的選單 → **直接生效，不經 Steps 6~6.7 過濾**
   - `module_only_codes`: 純模組注入的選單 → 經 Steps 6~6.7 過濾
4. **Step 3** 主查詢: `is_deleted=false` + `secure_code in allowed_codes`
5. **Step 5** RBAC: `required_permission` 欄位過濾
6. **Step 6** 合約過濾: `_filter_with_bypass()` 只過濾 `module_only_codes`，SYSTEM_ADMIN 完全豁免
7. **Step 6.5** 模組使用權: `_filter_with_bypass()` 只過濾 `module_only_codes`，SYSTEM_ADMIN/ORG_ADMIN 豁免
8. **Step 6.7** 子系統社群過濾: `_filter_with_bypass()` 只過濾 `module_only_codes`，SYSTEM_ADMIN/ORG_ADMIN 豁免

**`_filter_with_bypass()` 分流器**: 靜態方法，將 items 分為受管轄 (subject) 與不受管轄兩組，只對受管轄組執行過濾，最後合併保持原始順序。

**system.local 合約豁免**: `_get_authorized_modules()` 對 `SYSTEM_ORG_CODE` 直接回傳所有已安裝模組，不查合約。與 `Organization.get_contract_valid_range()` 永久有效邏輯一致。

**`SYSTEM_ORG_CODE` 集中化**: 所有 system.local 判斷統一從 `backend/app/constants.py` 匯入常數，不再分散定義。

### module_menu_service.py is_deleted 查詢邏輯

`_register_menu_item` 查詢包含已刪除記錄 (`filter_by(code=code, org_secure_code=SYSTEM_ORG_CODE)`)，然後檢查 `if existing and existing.is_deleted: return`。邏輯正確：被管理員刪除的選單不會被同步重建。

### module_access API 授權

所有端點使用 `@admin_required`，GET/POST 正確使用 `current_user.org_secure_code` 做租戶隔離。DELETE 的租戶隔離問題已在 SEC-01 中修正。

### module_access_control 測試殘留

5 筆 soft-deleted 記錄 (id 1,2,3,4,8) 為開發測試殘留，已被正確 soft-delete，unique 約束的 partial index (`WHERE is_deleted=false`) 確保不影響功能。保留不處理。

### 其他 commit 審查

其餘 24 筆 commit (分類/規格/頁面設計/主題/form.io 等) 與權限系統無關，未發現安全問題。

---

## 修改檔案清單

| 檔案 | 變更類型 |
|---|---|
| `backend/app/services/module_access_service.py` | 修正: remove_access 加入 org_secure_code |
| `backend/app/api/module_access.py` | 修正: 傳入 org_secure_code |
| `backend/app/services/menu_service.py` | 修正: 移除 _filter_by_module_access 的 rollback |
| `backend/app/services/module_menu_service.py` | 修正: deactivate/get 前綴匹配精確化 |
| `scripts/migrations/032_web_builder_menus.sql` | 修正: 移除不再需要的 MenuPermission 建立 |
| `scripts/migrations/033_security_audit_cleanup.sql` | 新增: DB 資料清理 migration |

## DB 直接變更

- soft-delete 18 筆孤兒 MenuPermission
- soft-delete 2 筆 org_hidden_functions 的 EMPLOYEE/EXTERNAL MenuPermission
