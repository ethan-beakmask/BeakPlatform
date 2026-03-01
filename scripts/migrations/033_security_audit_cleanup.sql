-- 033_security_audit_cleanup.sql
-- 安全審查後的資料清理
-- 審查範圍: 2026/02/26 ~ 2026/03/02 的所有變更
-- 日期: 2026-03-02

BEGIN;

-- 1. 軟刪除已刪除選單的孤兒 MenuPermissions
-- 背景: 選單被 soft-delete 後，對應的 MenuPermission 未一併處理
-- 影響: 無功能影響 (主查詢過濾 is_deleted=false)，但為死資料
UPDATE menu_permissions
SET is_deleted = true, deleted_at = NOW()
WHERE menu_secure_code IN (
    SELECT mi.secure_code FROM menu_items mi
    WHERE mi.is_deleted = true
)
AND is_deleted = false;

-- 2. 移除 org_hidden_functions 對 EMPLOYEE/EXTERNAL 的可見性
-- 背景: 此 header (暫時隱藏功能) 子項幾乎全部已刪除，不應對一般用戶可見
UPDATE menu_permissions
SET is_deleted = true, deleted_at = NOW()
WHERE menu_secure_code = (
    SELECT secure_code FROM menu_items
    WHERE code = 'org_hidden_functions' AND is_deleted = false
    LIMIT 1
)
AND user_type IN ('EMPLOYEE', 'EXTERNAL')
AND is_deleted = false;

COMMIT;
