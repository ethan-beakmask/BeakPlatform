-- ============================================================
-- 006: Two-Level Categories — 分類改為二層結構
-- ============================================================

-- 1. fw_categories 新增 parent_secure_code 欄位
ALTER TABLE fw_categories
    ADD COLUMN IF NOT EXISTS parent_secure_code VARCHAR(32);

CREATE INDEX IF NOT EXISTS idx_fw_categories_parent ON fw_categories(parent_secure_code);

-- 2. 調整唯一約束：同層同名不可重複
--    先刪除舊約束
ALTER TABLE fw_categories DROP CONSTRAINT IF EXISTS fw_categories_name_org_unique;

--    建立新約束：(name, parent_secure_code, org_secure_code) 唯一 (WHERE not deleted)
CREATE UNIQUE INDEX IF NOT EXISTS fw_categories_name_parent_org_unique
    ON fw_categories (name, COALESCE(parent_secure_code, ''), COALESCE(org_secure_code, ''))
    WHERE is_deleted = FALSE;

-- 3. fw_form_templates 新增 category_secure_code 欄位
ALTER TABLE fw_form_templates
    ADD COLUMN IF NOT EXISTS category_secure_code VARCHAR(32);

CREATE INDEX IF NOT EXISTS idx_fw_form_templates_category_sc ON fw_form_templates(category_secure_code);

-- 4. fw_workflow_templates 新增 category_secure_code 欄位
ALTER TABLE fw_workflow_templates
    ADD COLUMN IF NOT EXISTS category_secure_code VARCHAR(32);

CREATE INDEX IF NOT EXISTS idx_fw_workflow_templates_category_sc ON fw_workflow_templates(category_secure_code);

-- 5. 遷移表單 category 字串 → 對應父分類的 secure_code
--    （靈活結構：category_secure_code 可指向父或子分類）
UPDATE fw_form_templates ft
SET category_secure_code = parent.secure_code
FROM fw_categories parent
WHERE ft.category = parent.name
  AND parent.parent_secure_code IS NULL
  AND parent.is_deleted = FALSE
  AND (ft.category_secure_code IS NULL OR ft.category_secure_code = '');

-- 6. 遷移流程 category 字串 → 對應父分類的 secure_code
UPDATE fw_workflow_templates wt
SET category_secure_code = parent.secure_code
FROM fw_categories parent
WHERE wt.category = parent.name
  AND parent.parent_secure_code IS NULL
  AND parent.is_deleted = FALSE
  AND (wt.category_secure_code IS NULL OR wt.category_secure_code = '');

-- 8. 添加註解
COMMENT ON COLUMN fw_categories.parent_secure_code IS '父分類 secure_code，NULL 表示第一層分類';
COMMENT ON COLUMN fw_form_templates.category_secure_code IS '分類 secure_code (外鍵)';
COMMENT ON COLUMN fw_workflow_templates.category_secure_code IS '分類 secure_code (外鍵)';
