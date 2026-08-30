-- 123: Node grants menu entry
--
-- 新增 SYSTEM_ADMIN 專用的流程節點企業授權管理入口。

BEGIN;

SET LOCAL app.is_system_admin = 'true';

INSERT INTO menu_items (org_secure_code, module_secure_code, code, title, icon,
    link_type, link_target, open_in_new_tab, display_order, depth, is_expanded,
    is_active, required_level, is_shared, title_i18n, is_user_created,
    secure_code, is_deleted, created_at, updated_at, parent_secure_code)
SELECT 'system.local', NULL, 'node_grants', '節點授權', NULL,
       'route', 'node_grants.index', false,
       COALESCE((
           SELECT MAX(child.display_order) + 1
           FROM menu_items child
           WHERE child.parent_secure_code = parent.secure_code
             AND child.is_deleted = false
       ), 0),
       1, false, true, 0, false, '{"en": "Node Authorization"}'::jsonb, false,
       'NGMENU' || substr(md5('node_grants_123'), 1, 15),
       false, NOW(), NOW(), parent.secure_code
FROM menu_items parent
WHERE parent.code = 'perm_mgmt'
  AND parent.is_deleted = false
  AND NOT EXISTS (
      SELECT 1 FROM menu_items existing
      WHERE existing.code = 'node_grants'
        AND existing.is_deleted = false
  )
ON CONFLICT DO NOTHING;

INSERT INTO menu_permissions (secure_code, menu_secure_code, user_type, is_deleted, created_at, updated_at)
SELECT 'MP' || substr(md5(mi.code || '_perm_123'), 1, 20),
       mi.secure_code,
       'SYSTEM_ADMIN',
       false, NOW(), NOW()
FROM menu_items mi
WHERE mi.code = 'node_grants'
  AND mi.is_deleted = false
  AND NOT EXISTS (
      SELECT 1 FROM menu_permissions mp
      WHERE mp.menu_secure_code = mi.secure_code
        AND mp.user_type = 'SYSTEM_ADMIN'
        AND mp.is_deleted = false
  )
ON CONFLICT DO NOTHING;

COMMIT;
