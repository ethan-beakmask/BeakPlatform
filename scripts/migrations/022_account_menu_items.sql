-- 022_account_menu_items.sql
-- 新增帳號管理選單項目

-- 1. 將「用戶帳號」改為「員工帳號」
UPDATE menu_items
SET title = '員工帳號'
WHERE title = '用戶帳號' AND org_secure_code = 'system.local';

-- 2. 新增「企業管理員」選單項目
INSERT INTO menu_items (
    secure_code, org_secure_code, code, title, link_type, link_target,
    display_order, depth, is_active, required_level, open_in_new_tab, is_expanded, is_deleted,
    is_shared, is_user_created, created_at, updated_at
) VALUES (
    'ORG_ADMIN_MENU_' || SUBSTRING(md5(random()::text), 1, 16),
    'system.local', 'org_admins', '企業管理員', 'ROUTE', 'org_admins.list_admins',
    59, 0, true, 20, false, false, false,
    false, false, NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- 3. 新增「外部廠商」選單項目
INSERT INTO menu_items (
    secure_code, org_secure_code, code, title, link_type, link_target,
    display_order, depth, is_active, required_level, open_in_new_tab, is_expanded, is_deleted,
    is_shared, is_user_created, created_at, updated_at
) VALUES (
    'EXT_USER_MENU_' || SUBSTRING(md5(random()::text), 1, 16),
    'system.local', 'external_users', '外部廠商', 'ROUTE', 'external_users.list_external_users',
    60, 0, true, 20, false, false, false,
    false, false, NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- 調整原本的「員工帳號」(原用戶帳號) display_order，讓三個帳號管理放一起
UPDATE menu_items
SET display_order = 58
WHERE title = '員工帳號' AND org_secure_code = 'system.local';

-- 完成訊息
SELECT '帳號管理選單項目已新增' AS message;
