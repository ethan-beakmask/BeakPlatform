# SEC-02: SYSTEM_ADMIN 特權移除記錄

**日期**: 2026-03-14
**原因**: SYSTEM_ADMIN 不應享有跳過權限檢查的特權

## 移除清單

### 1. `backend/app/security/decorators.py` - `module_access_required`
- **原行為**: SYSTEM_ADMIN 跳過合約驗證 + ACL 檢查，直接放行
- **新行為**: 與其他用戶相同流程（合約驗證 -> 管理員檢查 -> ACL 檢查）
- **影響**: SYSTEM_ADMIN 存取模組功能需要企業有有效合約

### 2. `backend/app/services/permission_service.py` - `check_permission`
- **原行為**: `user.is_system_admin` 直接返回 True（跳過所有 RBAC 檢查）
- **新行為**: 走正常 RBAC 流程，依角色指派的權限決定
- **影響**: SYSTEM_ADMIN 需要透過角色指派取得 RBAC 權限

### 3. `backend/app/services/permission_service.py` - `get_all_permission_codes`
- **原行為**: SYSTEM_ADMIN 返回所有權限代碼
- **新行為**: 走正常流程，依角色指派取得權限代碼
- **影響**: 選單 `required_permission` 過濾會對 SYSTEM_ADMIN 生效

### 4. `backend/app/services/page_permission_service.py` - `check_page_access`
- **原行為**: `user.is_system_admin` 直接返回 ACCESS_FULL
- **新行為**: SYSTEM_ADMIN 可存取 `system_admin` + `authenticated` + `public` 等級頁面，但不自動通過 `org_admin` 等級
- **影響**: SYSTEM_ADMIN 無法存取 `org_admin` 等級的動態頁面

### 5. `backend/app/services/page_permission_service.py` - `get_user_accessible_pages`
- **原行為**: SYSTEM_ADMIN 可見所有頁面
- **新行為**: SYSTEM_ADMIN 可見 `system_admin` + `authenticated` + `public` 等級頁面
- **影響**: SYSTEM_ADMIN 的可見頁面列表縮小

## 未移除的（合理保留）

| 位置 | 說明 | 保留原因 |
|------|------|---------|
| `decorators.py` - `@system_admin_required` | 檢查 `is_system_admin` | 這是角色檢查，不是特權繞過 |
| `menu_service.py` - SYSTEM_ADMIN 不注入模組選單 | 獨立選單體系 | 設計決策，非特權 |
| `web/hostconfig.py` - `SET LOCAL app.is_system_admin` | RLS 繞過 | 系統管理頁面需要跨企業操作 |
| `lookup_service.py` - `SET LOCAL app.is_system_admin` | RLS 繞過 | 通用選項清單為系統級資料 |

## 回滾方式

如需回滾某個移除項目，在對應位置加回 SYSTEM_ADMIN 判斷。
每個移除點都有 `[SEC-02]` 標記可搜尋定位。
