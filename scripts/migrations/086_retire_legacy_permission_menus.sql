-- 086: Retire legacy permission management menu entries
--
-- Access Center 已取代舊權限中央、角色管理與帳號角色指派頁。
-- 本 migration 軟刪舊選單及其 Key1/Key2 授權資料，並從 menu_defaults
-- 移除對應預設列，避免恢復預設後舊入口重新出現。

BEGIN;

-- ============================================================
-- 1. 軟刪舊選單
-- ============================================================
UPDATE menu_items
SET is_deleted = true,
    deleted_at = NOW(),
    updated_at = NOW()
WHERE code IN ('permission_central', 'permission_central_org', 'roles', 'account_roles')
  AND is_deleted = false;

-- ============================================================
-- 2. 連帶軟刪舊選單 Key1 / Key2 授權
-- ============================================================
UPDATE menu_permissions mp
SET is_deleted = true,
    deleted_at = NOW(),
    updated_at = NOW()
FROM menu_items mi
WHERE mp.menu_secure_code = mi.secure_code
  AND mi.code IN ('permission_central', 'permission_central_org', 'roles', 'account_roles')
  AND mp.is_deleted = false;

UPDATE menu_role_requirements mrr
SET is_deleted = true,
    deleted_at = NOW(),
    updated_at = NOW()
FROM menu_items mi
WHERE mrr.menu_secure_code = mi.secure_code
  AND mi.code IN ('permission_central', 'permission_central_org', 'roles', 'account_roles')
  AND mrr.is_deleted = false;

-- ============================================================
-- 3. menu_defaults 移除舊入口
-- ============================================================
DELETE FROM menu_defaults
WHERE code IN ('permission_central', 'permission_central_org', 'roles', 'account_roles');

COMMIT;

-- 驗證：
-- SELECT code, is_deleted, deleted_at FROM menu_items WHERE code IN ('permission_central', 'permission_central_org', 'roles', 'account_roles');
-- SELECT count(*) FROM menu_permissions mp JOIN menu_items mi ON mi.secure_code = mp.menu_secure_code WHERE mi.code IN ('permission_central', 'permission_central_org', 'roles', 'account_roles') AND mp.is_deleted = false;  -- 0
-- SELECT count(*) FROM menu_role_requirements mrr JOIN menu_items mi ON mi.secure_code = mrr.menu_secure_code WHERE mi.code IN ('permission_central', 'permission_central_org', 'roles', 'account_roles') AND mrr.is_deleted = false;  -- 0
-- SELECT count(*) FROM menu_defaults WHERE code IN ('permission_central', 'permission_central_org', 'roles', 'account_roles');  -- 0
