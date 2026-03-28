-- 049: 新增緊急廣播管理選單（企業管理 > 緊急廣播管理）

-- 新增選單項
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
    'BYB5IqmunA3lcCrROPrifv',
    'system.local',
    false, false, false, NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM menu_items WHERE code = 'alert_broadcasts_org'
);

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
