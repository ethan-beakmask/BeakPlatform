-- 084: PERM-01 Phase B「選單即授權」方案 B
--
-- 1. 將掛有 @admin_required 之各區的 route 型選單 link_target 由 endpoint 名稱
--    改為 URL 路徑（link_type='url'），使 PageRoleGuard 的前綴匹配罩住整區
--    （create/edit/delete 等子路由），web 層即可移除 @admin_required。
-- 2. 補三個孤兒頁的選單項目：positions（職位設定）、delegations（代理授權）、
--    units（組織單位），Key1=ORG_ADMIN，Key2 複製 users 選單的各企業 ORG_ADMIN 角色。
-- 3. menu_defaults（factory 還原預設）同步更新，避免還原後退回 endpoint 匹配。

BEGIN;

-- ============================================================
-- 1. route(endpoint) -> url(path) 轉換
-- ============================================================
WITH conv(code, new_target) AS (VALUES
    ('system_settings',        '/admin/settings'),
    ('module_perm_mgmt',       '/admin/module-permissions'),
    ('org_admins',             '/admin/org-admins'),
    ('org_databases_org',      '/admin/org-database'),
    ('account_roles',          '/admin/account-roles/'),
    ('departments',            '/admin/departments/'),
    ('groups',                 '/admin/groups/'),
    ('numbering',              '/admin/numbering'),
    ('roles',                  '/roles/'),
    ('users',                  '/users/'),
    ('work_schedules',         '/admin/settings/work-schedules'),
    ('external_users',         '/external-users'),
    ('job_matrix',             '/job-levels/matrix'),
    ('job_levels',             '/job-levels/'),
    ('job_families',           '/job-families/'),
    ('job_titles',             '/job-titles/'),
    ('job_approval_categories','/job-approval-categories/')
)
UPDATE menu_items mi
SET link_type = 'url', link_target = c.new_target, updated_at = NOW()
FROM conv c
WHERE mi.code = c.code AND mi.is_deleted = false;

WITH conv(code, new_target) AS (VALUES
    ('system_settings',        '/admin/settings'),
    ('module_perm_mgmt',       '/admin/module-permissions'),
    ('org_admins',             '/admin/org-admins'),
    ('org_databases_org',      '/admin/org-database'),
    ('account_roles',          '/admin/account-roles/'),
    ('departments',            '/admin/departments/'),
    ('groups',                 '/admin/groups/'),
    ('numbering',              '/admin/numbering'),
    ('roles',                  '/roles/'),
    ('users',                  '/users/'),
    ('work_schedules',         '/admin/settings/work-schedules'),
    ('external_users',         '/external-users'),
    ('job_matrix',             '/job-levels/matrix'),
    ('job_levels',             '/job-levels/'),
    ('job_families',           '/job-families/'),
    ('job_titles',             '/job-titles/'),
    ('job_approval_categories','/job-approval-categories/')
)
UPDATE menu_defaults md
SET link_type = 'url', link_target = c.new_target, saved_at = NOW()
FROM conv c
WHERE md.code = c.code;

-- ============================================================
-- 2. 孤兒頁補選單
--    positions  -> 職級職稱 (jobs_config) 群組，display_order 5
--    delegations-> 帳號管理 (org_account) 群組，display_order 5
--    units      -> 頂層，排在 社群設定(15) 之後
-- ============================================================
INSERT INTO menu_items (org_secure_code, module_secure_code, code, title, icon,
    link_type, link_target, open_in_new_tab, display_order, depth, is_expanded,
    is_active, required_level, is_shared, title_i18n, is_user_created,
    secure_code, is_deleted, created_at, updated_at)
VALUES
    ('system.local', NULL, 'positions', '職位設定', NULL,
     'url', '/positions/', false, 5, 1, false,
     true, 30, false, '{"en": "Position Settings"}'::jsonb, false,
     'POSMENU' || substr(md5('positions_084'), 1, 15), false, NOW(), NOW()),
    ('system.local', NULL, 'delegations', '代理授權', NULL,
     'url', '/delegations/', false, 5, 1, false,
     true, 30, false, '{"en": "Delegation Authorization"}'::jsonb, false,
     'DLGMENU' || substr(md5('delegations_084'), 1, 15), false, NOW(), NOW()),
    ('system.local', NULL, 'units', '組織單位', NULL,
     'url', '/units/', false, 16, 0, false,
     true, 30, false, '{"en": "Organizational Units"}'::jsonb, false,
     'UNTMENU' || substr(md5('units_084'), 1, 15), false, NOW(), NOW());

UPDATE menu_items SET parent_secure_code =
    (SELECT secure_code FROM menu_items WHERE code = 'jobs_config' AND is_deleted = false)
WHERE code = 'positions' AND is_deleted = false;

UPDATE menu_items SET parent_secure_code =
    (SELECT secure_code FROM menu_items WHERE code = 'org_account' AND is_deleted = false)
WHERE code = 'delegations' AND is_deleted = false;

-- Key1: ORG_ADMIN
INSERT INTO menu_permissions (secure_code, menu_secure_code, user_type, is_deleted, created_at, updated_at)
SELECT 'MP' || substr(md5(mi.code || '_perm_084'), 1, 20), mi.secure_code, 'ORG_ADMIN', false, NOW(), NOW()
FROM menu_items mi
WHERE mi.code IN ('positions', 'delegations', 'units') AND mi.is_deleted = false;

-- Key2: 複製 users 選單的各企業角色需求（各企業 ORG_ADMIN 角色）
INSERT INTO menu_role_requirements (secure_code, menu_secure_code, org_secure_code, role_secure_code, is_deleted, created_at, updated_at)
SELECT 'MRR' || substr(md5(mi.code || src.org_secure_code || '_084'), 1, 19),
       mi.secure_code, src.org_secure_code, src.role_secure_code, false, NOW(), NOW()
FROM menu_items mi
CROSS JOIN (
    SELECT mrr.org_secure_code, mrr.role_secure_code
    FROM menu_role_requirements mrr
    JOIN menu_items u ON u.secure_code = mrr.menu_secure_code
    WHERE u.code = 'users' AND u.is_deleted = false AND mrr.is_deleted = false
) src
WHERE mi.code IN ('positions', 'delegations', 'units') AND mi.is_deleted = false;

-- menu_defaults 同步補三筆
INSERT INTO menu_defaults (code, title, title_i18n, icon, link_type, link_target,
    display_order, depth, parent_code, is_expanded, is_shared, required_permission,
    user_types, role_codes, saved_by, saved_at)
VALUES
    ('positions', '職位設定', '{"en": "Position Settings"}'::jsonb, NULL, 'url', '/positions/',
     5, 1, 'jobs_config', false, false, NULL,
     '["ORG_ADMIN"]'::jsonb, '["ORG_ADMIN"]'::jsonb, 'migration_084', NOW()),
    ('delegations', '代理授權', '{"en": "Delegation Authorization"}'::jsonb, NULL, 'url', '/delegations/',
     5, 1, 'org_account', false, false, NULL,
     '["ORG_ADMIN"]'::jsonb, '["ORG_ADMIN"]'::jsonb, 'migration_084', NOW()),
    ('units', '組織單位', '{"en": "Organizational Units"}'::jsonb, NULL, 'url', '/units/',
     17, 0, NULL, false, false, NULL,
     '["ORG_ADMIN"]'::jsonb, '["ORG_ADMIN"]'::jsonb, 'migration_084', NOW());

COMMIT;

-- 驗證：
-- SELECT code, link_type, link_target FROM menu_items WHERE is_deleted=false AND link_type='url' ORDER BY code;
-- SELECT count(*) FROM menu_items WHERE code IN ('positions','delegations','units') AND is_deleted=false;  -- 3
