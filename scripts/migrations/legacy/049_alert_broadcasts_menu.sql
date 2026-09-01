-- 049: 新增緊急廣播管理選單（企業管理 > 緊急廣播管理）
-- 注意: 全新安裝時由 init_menus.py 建立，此 migration 僅供升級使用

-- 新增選單項 (僅在 org_config_mgr 存在時執行，即升級情境)
INSERT INTO menu_items (
    secure_code, code, title, icon, link_type, link_target,
    open_in_new_tab, display_order, depth, is_expanded, is_active,
    required_level, parent_secure_code, org_secure_code, is_shared, is_deleted, is_user_created, created_at, updated_at
)
SELECT
    encode(gen_random_bytes(16), 'hex'),
    'alert_broadcasts_org',
    '緊急廣播管理',
    'ri-alarm-warning-line',
    'url',
    '/security/alert-broadcasts/',
    false, 57, 1, false, true, 30,
    (SELECT secure_code FROM menu_items WHERE code = 'org_config_mgr' AND is_deleted = false LIMIT 1),
    (SELECT secure_code FROM organizations WHERE code = 'SYSTEM' LIMIT 1),
    false, false, false, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM menu_items WHERE code = 'alert_broadcasts_org')
  AND EXISTS (SELECT 1 FROM menu_items WHERE code = 'org_config_mgr' AND is_deleted = false);

-- 新增選單權限 (ORG_ADMIN)
INSERT INTO menu_permissions (secure_code, menu_secure_code, user_type, is_deleted, created_at, updated_at)
SELECT
    encode(gen_random_bytes(16), 'hex'),
    mi.secure_code,
    'ORG_ADMIN',
    false, NOW(), NOW()
FROM menu_items mi
WHERE mi.code = 'alert_broadcasts_org'
  AND NOT EXISTS (
    SELECT 1 FROM menu_permissions mp
    WHERE mp.menu_secure_code = mi.secure_code AND mp.user_type = 'ORG_ADMIN'
  );
