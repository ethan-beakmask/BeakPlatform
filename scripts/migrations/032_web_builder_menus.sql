-- 032_web_builder_menus.sql
-- Web Builder 模組選單入口
--
-- web_builder 模組與 data_crud 共用底層程式碼，但在選單上是獨立模組。
-- 選單 code 以 web_builder 開頭，才能被 _get_module_code_for_menu() 識別。
-- 只有被指派 web_builder 模組使用權的開發者才會看到這些選單。

BEGIN;

-- 1. 建立 web_builder 頂級選單 (header)
INSERT INTO menu_items (
    secure_code, org_secure_code, code, title,
    title_i18n, title_en, title_zh_cn,
    icon, link_type, link_target,
    open_in_new_tab, required_level,
    parent_secure_code, display_order, depth,
    is_expanded, is_active, is_shared, is_user_created,
    is_deleted, created_at, updated_at
) VALUES (
    'WB_MENU_HDR_' || substr(md5(random()::text), 1, 16),
    'system.local',
    'web_builder',
    'Web Builder',
    '{"en": "Web Builder", "zh-CN": "Web Builder"}',
    'Web Builder',
    'Web Builder',
    NULL,
    'header',
    NULL,
    false,
    2,
    NULL,
    185,   -- data_crud(180) 之後
    0,
    false,
    true,
    true,
    false,
    false,
    NOW(),
    NOW()
)
ON CONFLICT DO NOTHING;

-- 2. 建立子系統管理子選單
INSERT INTO menu_items (
    secure_code, org_secure_code, code, title,
    title_i18n, title_en, title_zh_cn,
    icon, link_type, link_target,
    open_in_new_tab, required_level,
    parent_secure_code, display_order, depth,
    is_expanded, is_active, is_shared, is_user_created,
    is_deleted, created_at, updated_at
) VALUES (
    'WB_MENU_SUB_' || substr(md5(random()::text), 1, 16),
    'system.local',
    'web_builder.sub_systems',
    '子系統管理',
    '{"en": "Sub-Systems", "zh-CN": "子系统管理"}',
    'Sub-Systems',
    '子系统管理',
    NULL,
    'route',
    '/data-crud/sub-systems',
    false,
    2,
    (SELECT secure_code FROM menu_items WHERE code = 'web_builder' AND is_deleted = false LIMIT 1),
    1,
    1,
    false,
    true,
    true,
    false,
    false,
    NOW(),
    NOW()
)
ON CONFLICT DO NOTHING;

-- 3. 建立設計器子選單
INSERT INTO menu_items (
    secure_code, org_secure_code, code, title,
    title_i18n, title_en, title_zh_cn,
    icon, link_type, link_target,
    open_in_new_tab, required_level,
    parent_secure_code, display_order, depth,
    is_expanded, is_active, is_shared, is_user_created,
    is_deleted, created_at, updated_at
) VALUES (
    'WB_MENU_LAB_' || substr(md5(random()::text), 1, 16),
    'system.local',
    'web_builder.lab',
    '設計器',
    '{"en": "Designer", "zh-CN": "设计器"}',
    'Designer',
    '设计器',
    NULL,
    'route',
    '/data-crud/lab',
    false,
    2,
    (SELECT secure_code FROM menu_items WHERE code = 'web_builder' AND is_deleted = false LIMIT 1),
    2,
    1,
    false,
    true,
    true,
    false,
    false,
    NOW(),
    NOW()
)
ON CONFLICT DO NOTHING;

-- 4. MenuPermission 不再需要
-- web_builder 選單可見性改由 module_access_control 動態注入驅動
-- (SYSTEM_ADMIN/ORG_ADMIN 自動看到所有已安裝模組，EMPLOYEE 按 ACL)
-- 參考: menu_service.py Step 1.5

COMMIT;
