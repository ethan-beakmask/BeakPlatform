-- 038: 擴大 menu_items.icon 欄位以支援 Remix Icon class name
-- 原本 VARCHAR(10) 不足以容納 ri-database-2-line 等 class name
-- 2026-03-14

ALTER TABLE menu_items ALTER COLUMN icon TYPE VARCHAR(50);

-- 修正既有模組 icon 值
UPDATE menu_items SET icon = 'ri-database-2-line' WHERE code = 'nocode_builder' AND is_deleted = FALSE;
UPDATE menu_items SET icon = 'ri-flow-chart' WHERE code = 'form_workflow' AND is_deleted = FALSE;
UPDATE menu_items SET icon = 'ri-file-list-line' WHERE code = 'spec_formulate' AND is_deleted = FALSE;
