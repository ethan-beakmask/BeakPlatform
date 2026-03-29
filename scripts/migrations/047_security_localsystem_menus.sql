-- 047: 新增「本機安全」選單 (security_localsystem)
-- 系統區: 根選單 + 登入錯誤監看子選單 (SYSTEM_ADMIN)
-- 企業區: 掛在 org_config_mgr 下 (ORG_ADMIN)

-- ============================================================
-- 1. 系統區根選單: security_localsystem
-- ============================================================
INSERT INTO menu_items (
    secure_code, org_secure_code, code, title, icon, link_type, link_target,
    display_order, depth, is_active, required_level, open_in_new_tab, is_expanded, is_deleted,
    is_shared, is_user_created, parent_secure_code, module_secure_code,
    created_at, updated_at
) VALUES (
    'sec_localsys_root_001',
    (SELECT secure_code FROM organizations WHERE code = 'SYSTEM' LIMIT 1),
    'security_localsystem', '本機安全', 'bi-shield-lock', 'header', NULL,
    100, 0, true, 0, false, false, false,
    false, false, NULL, NULL,
    NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- MenuPermission: SYSTEM_ADMIN
INSERT INTO menu_permissions (
    secure_code, menu_secure_code, user_type, is_deleted, created_at, updated_at
) VALUES (
    'sec_localsys_perm_001',
    'sec_localsys_root_001', 'SYSTEM_ADMIN', false, NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- ============================================================
-- 2. 系統區子選單: login_fail_monitor (under security_localsystem)
-- ============================================================
INSERT INTO menu_items (
    secure_code, org_secure_code, code, title, icon, link_type, link_target,
    display_order, depth, is_active, required_level, open_in_new_tab, is_expanded, is_deleted,
    is_shared, is_user_created, parent_secure_code, module_secure_code,
    created_at, updated_at
) VALUES (
    'sec_loginfail_sys_001',
    (SELECT secure_code FROM organizations WHERE code = 'SYSTEM' LIMIT 1),
    'login_fail_monitor', '登入錯誤監看', 'bi-shield-exclamation', 'url', '/security/login-failures/',
    10, 1, true, 0, false, false, false,
    false, false, 'sec_localsys_root_001', NULL,
    NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- MenuPermission: SYSTEM_ADMIN
INSERT INTO menu_permissions (
    secure_code, menu_secure_code, user_type, is_deleted, created_at, updated_at
) VALUES (
    'sec_loginfail_perm_001',
    'sec_loginfail_sys_001', 'SYSTEM_ADMIN', false, NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- ============================================================
-- 3. 企業區子選單: login_fail_monitor_org (under org_config_mgr)
-- ============================================================
INSERT INTO menu_items (
    secure_code, org_secure_code, code, title, icon, link_type, link_target,
    display_order, depth, is_active, required_level, open_in_new_tab, is_expanded, is_deleted,
    is_shared, is_user_created, parent_secure_code, module_secure_code,
    created_at, updated_at
) VALUES (
    'sec_loginfail_org_001',
    (SELECT secure_code FROM organizations WHERE code = 'SYSTEM' LIMIT 1),
    'login_fail_monitor_org', '登入錯誤監看', 'bi-shield-exclamation', 'url', '/security/login-failures/',
    55, 1, true, 30, false, false, false,
    false, false, 'BYB5IqmunA3lcCrROPrifv', NULL,
    NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- MenuPermission: ORG_ADMIN
INSERT INTO menu_permissions (
    secure_code, menu_secure_code, user_type, is_deleted, created_at, updated_at
) VALUES (
    'sec_loginfail_perm_002',
    'sec_loginfail_org_001', 'ORG_ADMIN', false, NOW(), NOW()
) ON CONFLICT DO NOTHING;

SELECT '本機安全選單已建立' AS message;
