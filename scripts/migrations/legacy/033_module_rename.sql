-- =============================================================================
-- 033: Module Rename - data_crud -> nocode_builder, web_builder cleanup,
--      form_workflow.data_specs -> spec_formulate
-- =============================================================================
-- Date: 2026-03-13
-- Description:
--   1. Rename data_crud menu items to nocode_builder
--   2. Update menu titles (子系統管理->子系統開發, 頁面設計->頁面管理, etc.)
--   3. Update menu link_targets from /data-crud/ to /nocode-builder/
--   4. Update INSTALLED_MODULES lookup
--   5. Update contracts modules_config JSON
--   6. Update module_access_control
--   7. Rename form_workflow.data_specs to spec_formulate
--   8. Clean up web_builder zombie references
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. MenuItem: data_crud.* -> nocode_builder.*
-- =============================================================================

-- Root menu
UPDATE menu_items SET
    code = 'nocode_builder',
    title = '子系統開發模組',
    title_i18n = jsonb_set(COALESCE(title_i18n, '{}'), '{en}', '"NoCode Builder"'),
    title_en = 'NoCode Builder'
WHERE code = 'data_crud' AND is_deleted = false;

-- Sub systems (rename: 子系統管理 -> 子系統開發)
UPDATE menu_items SET
    code = 'nocode_builder.sub_systems',
    title = '子系統開發',
    title_i18n = jsonb_set(COALESCE(title_i18n, '{}'), '{en}', '"Sub System Development"'),
    title_en = 'Sub System Development',
    link_target = '/nocode-builder/sub-systems'
WHERE code = 'data_crud.sub_systems' AND is_deleted = false;

-- Views
UPDATE menu_items SET
    code = 'nocode_builder.views',
    title_i18n = jsonb_set(COALESCE(title_i18n, '{}'), '{en}', '"View Manager"'),
    link_target = '/nocode-builder/'
WHERE code = 'data_crud.views' AND is_deleted = false;

-- Lab (rename: 頁面設計 -> 頁面管理)
UPDATE menu_items SET
    code = 'nocode_builder.lab',
    title = '頁面管理',
    title_i18n = jsonb_set(COALESCE(title_i18n, '{}'), '{en}', '"Page Manager"'),
    title_en = 'Page Manager',
    link_target = '/nocode-builder/lab'
WHERE code = 'data_crud.lab' AND is_deleted = false;

-- Lookup
UPDATE menu_items SET
    code = 'nocode_builder.lookup',
    title_i18n = jsonb_set(COALESCE(title_i18n, '{}'), '{en}', '"Lookup List"'),
    link_target = '/nocode-builder/lookup'
WHERE code = 'data_crud.lookup' AND is_deleted = false;

-- Dynamic sub-system menus created by provision_service
UPDATE menu_items SET
    link_target = REPLACE(link_target, '/data-crud/', '/nocode-builder/')
WHERE link_target LIKE '/data-crud/%' AND is_deleted = false;

-- =============================================================================
-- 2. form_workflow.data_specs -> spec_formulate
-- =============================================================================

UPDATE menu_items SET
    code = 'spec_formulate',
    title = '規格制定模組',
    title_i18n = jsonb_set(COALESCE(title_i18n, '{}'), '{en}', '"Spec Formulate"'),
    title_en = 'Spec Formulate',
    link_target = NULL,
    parent_secure_code = NULL,
    depth = 0,
    icon = 'S',
    display_order = 150
WHERE code = 'form_workflow.data_specs' AND is_deleted = false;

-- Create child menu: spec_formulate.data_specs
-- (Reuse existing record by adding a child, or let module_loader sync handle it)

-- =============================================================================
-- 3. INSTALLED_MODULES lookup
-- =============================================================================

-- data_crud -> nocode_builder
UPDATE lookup_items SET
    code = 'nocode_builder',
    label = '子系統開發模組',
    label_i18n = '{"en": "NoCode Builder", "zh-TW": "子系統開發模組"}'::jsonb,
    value = jsonb_set(
        jsonb_set(value, '{description}', '"無碼子系統開發平台：視圖管理、頁面管理、子系統開發、選項清單"'),
        '{version}', '"2.0.0"'
    )
WHERE category_code = 'INSTALLED_MODULES' AND code = 'data_crud' AND is_deleted = false;

-- Remove web_builder (zombie)
UPDATE lookup_items SET is_deleted = true, deleted_at = NOW()
WHERE category_code = 'INSTALLED_MODULES' AND code = 'web_builder' AND is_deleted = false;

-- Add spec_formulate (if not exists)
INSERT INTO lookup_items (
    secure_code, category_code, code, label, label_i18n, value,
    sort_order, is_active, is_deleted, created_at, updated_at
)
SELECT
    'spec_formulate_' || substr(md5(random()::text), 1, 16),
    'INSTALLED_MODULES',
    'spec_formulate',
    '規格制定模組',
    '{"en": "Spec Formulate", "zh-TW": "規格制定模組"}'::jsonb,
    '{"enabled": true, "version": "1.0.0", "description": "資料表欄位規格定義與管理"}'::jsonb,
    20,
    true,
    false,
    NOW(),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM lookup_items
    WHERE category_code = 'INSTALLED_MODULES' AND code = 'spec_formulate' AND is_deleted = false
);

-- =============================================================================
-- 4. Contracts modules_config JSON
-- =============================================================================

-- Replace data_crud -> nocode_builder, web_builder -> nocode_builder in JSON arrays
-- Use Python-friendly approach: replace strings within JSON
UPDATE contracts SET
    modules_config = REPLACE(modules_config, '"data_crud"', '"nocode_builder"')
WHERE modules_config IS NOT NULL AND modules_config LIKE '%"data_crud"%';

UPDATE contracts SET
    modules_config = REPLACE(modules_config, '"web_builder"', '"nocode_builder"')
WHERE modules_config IS NOT NULL AND modules_config LIKE '%"web_builder"%';

-- Add spec_formulate to contracts that have form_workflow
-- (spec_formulate was part of form_workflow before)
UPDATE contracts SET
    modules_config = REPLACE(modules_config, '"form_workflow"', '"form_workflow","spec_formulate"')
WHERE modules_config IS NOT NULL
    AND modules_config LIKE '%"form_workflow"%'
    AND modules_config NOT LIKE '%"spec_formulate"%';

-- =============================================================================
-- 5. module_access_control
-- =============================================================================

UPDATE module_access_control SET module_code = 'nocode_builder'
WHERE module_code = 'web_builder' AND is_deleted = false;

UPDATE module_access_control SET module_code = 'nocode_builder'
WHERE module_code = 'data_crud' AND is_deleted = false;

-- =============================================================================
-- 6. Clean up web_builder zombie menus (if any remain)
-- =============================================================================

UPDATE menu_items SET is_deleted = true, deleted_at = NOW()
WHERE code LIKE 'web_builder%' AND is_deleted = false;

COMMIT;
