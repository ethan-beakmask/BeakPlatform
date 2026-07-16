-- 085: Access Center WP1 menu entries
--
-- 新增權限管理中心雙選單入口：
-- 1. access_center：SYSTEM_ADMIN，parent=perm_mgmt
-- 2. access_center_org：ORG_ADMIN，parent=roles_control，Key2 複製 users 選單各企業角色
-- 並同步 menu_defaults。

BEGIN;

-- ============================================================
-- 1. 新增兩筆 URL 型選單，display_order 排在各群組最後
-- ============================================================
INSERT INTO menu_items (org_secure_code, module_secure_code, code, title, icon,
    link_type, link_target, open_in_new_tab, display_order, depth, is_expanded,
    is_active, required_level, is_shared, title_i18n, is_user_created,
    secure_code, is_deleted, created_at, updated_at, parent_secure_code)
SELECT 'system.local', NULL, v.code, '權限管理中心', NULL,
       'url', '/access/', false,
       COALESCE((
           SELECT MAX(child.display_order) + 1
           FROM menu_items child
           WHERE child.parent_secure_code = parent.secure_code
             AND child.is_deleted = false
       ), 0),
       1, false, true, 30, false, '{"en": "Access Center"}'::jsonb, false,
       v.secure_code, false, NOW(), NOW(), parent.secure_code
FROM (VALUES
    ('access_center', 'perm_mgmt', 'ACMENU' || substr(md5('access_center_085'), 1, 15)),
    ('access_center_org', 'roles_control', 'ACOMENU' || substr(md5('access_center_org_085'), 1, 14))
) AS v(code, parent_code, secure_code)
JOIN menu_items parent ON parent.code = v.parent_code AND parent.is_deleted = false
WHERE NOT EXISTS (
    SELECT 1 FROM menu_items existing
    WHERE existing.code = v.code AND existing.is_deleted = false
);

-- Key1
INSERT INTO menu_permissions (secure_code, menu_secure_code, user_type, is_deleted, created_at, updated_at)
SELECT 'MP' || substr(md5(mi.code || '_perm_085'), 1, 20),
       mi.secure_code,
       CASE WHEN mi.code = 'access_center' THEN 'SYSTEM_ADMIN' ELSE 'ORG_ADMIN' END,
       false, NOW(), NOW()
FROM menu_items mi
WHERE mi.code IN ('access_center', 'access_center_org')
  AND mi.is_deleted = false
  AND NOT EXISTS (
      SELECT 1 FROM menu_permissions mp
      WHERE mp.menu_secure_code = mi.secure_code
        AND mp.user_type = CASE WHEN mi.code = 'access_center' THEN 'SYSTEM_ADMIN' ELSE 'ORG_ADMIN' END
        AND mp.is_deleted = false
  );

-- Key2: access_center_org 複製 users 選單的各企業角色需求
INSERT INTO menu_role_requirements (secure_code, menu_secure_code, org_secure_code, role_secure_code, is_deleted, created_at, updated_at)
SELECT 'MRR' || substr(md5(mi.code || src.org_secure_code || src.role_secure_code || '_085'), 1, 19),
       mi.secure_code, src.org_secure_code, src.role_secure_code, false, NOW(), NOW()
FROM menu_items mi
CROSS JOIN (
    SELECT mrr.org_secure_code, mrr.role_secure_code
    FROM menu_role_requirements mrr
    JOIN menu_items u ON u.secure_code = mrr.menu_secure_code
    WHERE u.code = 'users' AND u.is_deleted = false AND mrr.is_deleted = false
) src
WHERE mi.code = 'access_center_org'
  AND mi.is_deleted = false
  AND NOT EXISTS (
      SELECT 1 FROM menu_role_requirements existing
      WHERE existing.menu_secure_code = mi.secure_code
        AND existing.org_secure_code = src.org_secure_code
        AND existing.role_secure_code = src.role_secure_code
        AND existing.is_deleted = false
  );

-- ============================================================
-- 2. menu_defaults 同步
-- ============================================================
INSERT INTO menu_defaults (code, title, title_i18n, icon, link_type, link_target,
    display_order, depth, parent_code, is_expanded, is_shared, required_permission,
    user_types, role_codes, saved_by, saved_at)
SELECT v.code, '權限管理中心', '{"en": "Access Center"}'::jsonb, NULL, 'url', '/access/',
       COALESCE((
           SELECT MAX(md.display_order) + 1
           FROM menu_defaults md
           WHERE md.parent_code = v.parent_code
       ), 0),
       1, v.parent_code, false, false, NULL,
       v.user_types::jsonb, v.role_codes::jsonb, 'migration_085', NOW()
FROM (VALUES
    ('access_center', 'perm_mgmt', '["SYSTEM_ADMIN"]', '[]'),
    ('access_center_org', 'roles_control', '["ORG_ADMIN"]', '["ORG_ADMIN"]')
) AS v(code, parent_code, user_types, role_codes)
WHERE NOT EXISTS (
    SELECT 1 FROM menu_defaults md WHERE md.code = v.code
);

COMMIT;

-- 驗證：
-- SELECT code, link_type, link_target FROM menu_items WHERE code IN ('access_center', 'access_center_org') AND is_deleted=false;
-- SELECT code, parent_code, user_types, role_codes FROM menu_defaults WHERE code IN ('access_center', 'access_center_org');
