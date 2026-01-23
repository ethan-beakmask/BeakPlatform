-- ============================================================
-- 015_enterprise_defaults.sql
-- 企業預設值支援
-- ============================================================

-- 新增 is_system_unit 欄位到 organizational_units
ALTER TABLE organizational_units
ADD COLUMN IF NOT EXISTS is_system_unit BOOLEAN NOT NULL DEFAULT FALSE;

-- 欄位註解
COMMENT ON COLUMN organizational_units.is_system_unit IS '是否為系統保留單位（不可刪除）';

-- 新增 is_system_category 欄位到 form_categories
ALTER TABLE form_categories
ADD COLUMN IF NOT EXISTS is_system_category BOOLEAN NOT NULL DEFAULT FALSE;

-- 欄位註解
COMMENT ON COLUMN form_categories.is_system_category IS '是否為系統保留分類（不可刪除）';

-- ============================================================
-- 執行結果輸出
-- ============================================================
SELECT 'Migration 015_enterprise_defaults.sql completed successfully' AS status;
