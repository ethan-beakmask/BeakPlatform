-- 078: 「API Key 管理」選單(系統安全群組下)
-- 規格: docs/API_KEY_TRIGGER_SPEC.md §4
-- 注意: 全新安裝時由 init_menus.py(menu_defaults.py)建立，此 migration 僅供升級使用

INSERT INTO menu_items (
    secure_code, code, title, link_type, link_target,
    display_order, depth, required_level, icon, org_secure_code,
    parent_secure_code,
    is_shared, is_active, is_deleted, open_in_new_tab, is_expanded, is_user_created,
    created_at, updated_at
)
SELECT
    'sec_apikey_org_001', 'api_key_manage', 'API Key 管理', 'url',
    '/security/api-keys/',
    3, 1, 30, 'bi-key',
    (SELECT secure_code FROM organizations WHERE code = 'SYSTEM' LIMIT 1),
    (SELECT secure_code FROM menu_items WHERE code = 'org_security' AND is_deleted = false LIMIT 1),
    false, true, false, false, false, false,
    NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM menu_items WHERE code = 'api_key_manage')
  AND EXISTS (SELECT 1 FROM menu_items WHERE code = 'org_security' AND is_deleted = false);

-- 雙鑰匙選單安全: MenuPermission(ORG_ADMIN)
INSERT INTO menu_permissions (
    secure_code, menu_secure_code, user_type, is_deleted, created_at, updated_at
)
SELECT
    md5(random()::text || clock_timestamp()::text),
    (SELECT secure_code FROM menu_items WHERE code = 'api_key_manage' AND is_deleted = false LIMIT 1),
    'ORG_ADMIN', false, NOW(), NOW()
WHERE EXISTS (SELECT 1 FROM menu_items WHERE code = 'api_key_manage' AND is_deleted = false)
  AND NOT EXISTS (
    SELECT 1 FROM menu_permissions mp
    JOIN menu_items mi ON mi.secure_code = mp.menu_secure_code
    WHERE mi.code = 'api_key_manage' AND mp.is_deleted = false
  );
