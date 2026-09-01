-- 053: 企業級「系統安全」選單群組
-- 日期: 2026-03-24
-- 說明:
--   1. 新增「系統安全」根選單 (ORG_ADMIN level)
--   2. 將「登入錯誤監看」從「系統管理」移至「系統安全」
--   3. 新增「速率限制」子選單
-- 注意: 全新安裝時由 init_menus.py 建立，此 migration 僅供升級使用

-- 1. 新增「系統安全」根選單
INSERT INTO menu_items (
    secure_code, code, title, link_type, link_target,
    display_order, depth, required_level, icon, org_secure_code,
    is_shared, is_active, is_deleted, open_in_new_tab, is_expanded, is_user_created,
    created_at, updated_at
)
SELECT
    'sec_org_security_root', 'org_security', '系統安全', 'header', '',
    12, 0, 30, 'bi-shield-lock',
    (SELECT secure_code FROM organizations WHERE code = 'SYSTEM' LIMIT 1),
    false, true, false, false, false, false,
    NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM menu_items WHERE code = 'org_security')
  AND EXISTS (SELECT 1 FROM organizations WHERE code = 'SYSTEM');

-- 2. 移動「登入錯誤監看」到「系統安全」下 (僅升級時 sec_loginfail_org_001 存在)
UPDATE menu_items
SET parent_secure_code = (SELECT secure_code FROM menu_items WHERE code = 'org_security' AND is_deleted = false LIMIT 1),
    updated_at = NOW()
WHERE secure_code = 'sec_loginfail_org_001'
  AND EXISTS (SELECT 1 FROM menu_items WHERE code = 'org_security' AND is_deleted = false);

-- 3. 新增「速率限制」子選單
INSERT INTO menu_items (
    secure_code, code, title, link_type, link_target,
    display_order, depth, required_level, icon, org_secure_code,
    parent_secure_code,
    is_shared, is_active, is_deleted, open_in_new_tab, is_expanded, is_user_created,
    created_at, updated_at
)
SELECT
    'sec_ratelimit_org_001', 'org_rate_limits', '速率限制', 'url',
    '/security/rate-limits/',
    60, 1, 30, 'bi-speedometer2',
    (SELECT secure_code FROM organizations WHERE code = 'SYSTEM' LIMIT 1),
    (SELECT secure_code FROM menu_items WHERE code = 'org_security' AND is_deleted = false LIMIT 1),
    false, true, false, false, false, false,
    NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM menu_items WHERE code = 'org_rate_limits')
  AND EXISTS (SELECT 1 FROM menu_items WHERE code = 'org_security' AND is_deleted = false);
