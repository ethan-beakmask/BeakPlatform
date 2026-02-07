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

-- 5. 為每個現有父分類建立「其他」子分類
--    使用 pgcrypto 生成 secure_code (hex 格式, 22 字元)
DO $$
DECLARE
    parent_rec RECORD;
    new_sc TEXT;
BEGIN
    FOR parent_rec IN
        SELECT secure_code, org_secure_code
        FROM fw_categories
        WHERE parent_secure_code IS NULL
          AND is_deleted = FALSE
    LOOP
        -- 生成 secure_code
        new_sc := encode(gen_random_bytes(16), 'base64');
        new_sc := replace(replace(replace(new_sc, '+', '-'), '/', '_'), '=', '');

        -- 檢查此父分類下是否已有「其他」子分類
        IF NOT EXISTS (
            SELECT 1 FROM fw_categories
            WHERE parent_secure_code = parent_rec.secure_code
              AND name = '其他'
              AND is_deleted = FALSE
        ) THEN
            INSERT INTO fw_categories (
                secure_code, org_secure_code, parent_secure_code,
                name, description, display_order,
                is_system, show_in_form_design, show_in_workflow_design, show_in_form_center
            ) VALUES (
                new_sc, parent_rec.org_secure_code, parent_rec.secure_code,
                '其他', '未細分的項目', 999,
                FALSE, TRUE, TRUE, TRUE
            );
        END IF;
    END LOOP;
END $$;

-- 6. 遷移表單 category 字串 → 對應父分類下「其他」子分類的 secure_code
UPDATE fw_form_templates ft
SET category_secure_code = sub.secure_code
FROM fw_categories parent
JOIN fw_categories sub ON sub.parent_secure_code = parent.secure_code
    AND sub.name = '其他'
    AND sub.is_deleted = FALSE
WHERE ft.category = parent.name
  AND parent.parent_secure_code IS NULL
  AND parent.is_deleted = FALSE
  AND ft.category_secure_code IS NULL;

-- 7. 遷移流程 category 字串 → 對應父分類下「其他」子分類的 secure_code
UPDATE fw_workflow_templates wt
SET category_secure_code = sub.secure_code
FROM fw_categories parent
JOIN fw_categories sub ON sub.parent_secure_code = parent.secure_code
    AND sub.name = '其他'
    AND sub.is_deleted = FALSE
WHERE wt.category = parent.name
  AND parent.parent_secure_code IS NULL
  AND parent.is_deleted = FALSE
  AND wt.category_secure_code IS NULL;

-- 8. 添加註解
COMMENT ON COLUMN fw_categories.parent_secure_code IS '父分類 secure_code，NULL 表示第一層分類';
COMMENT ON COLUMN fw_form_templates.category_secure_code IS '分類 secure_code (外鍵)';
COMMENT ON COLUMN fw_workflow_templates.category_secure_code IS '分類 secure_code (外鍵)';
