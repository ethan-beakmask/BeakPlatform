-- FormWorkflow Module Migration: 建立分類表
-- 執行時間: 2026-01-28

-- 建立分類表
CREATE TABLE IF NOT EXISTS fw_categories (
    id BIGSERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32),  -- NULL 表示系統分類

    -- 基本資訊
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    display_order INTEGER DEFAULT 0,

    -- 系統內建標記
    is_system BOOLEAN DEFAULT FALSE NOT NULL,

    -- 顯示開關
    show_in_form_design BOOLEAN DEFAULT TRUE NOT NULL,
    show_in_workflow_design BOOLEAN DEFAULT TRUE NOT NULL,
    show_in_form_center BOOLEAN DEFAULT TRUE NOT NULL,

    -- 時間戳記
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,

    -- 唯一約束
    CONSTRAINT fw_categories_name_org_unique UNIQUE (name, org_secure_code)
);

-- 建立索引
CREATE INDEX IF NOT EXISTS idx_fw_categories_org ON fw_categories(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_categories_name ON fw_categories(name);
CREATE INDEX IF NOT EXISTS idx_fw_categories_display_order ON fw_categories(display_order);

-- 插入預設分類（系統分類，org_secure_code = NULL）
INSERT INTO fw_categories (secure_code, org_secure_code, name, description, display_order, is_system, show_in_form_design, show_in_workflow_design, show_in_form_center)
VALUES
    ('SYS_CAT_WORKFLOW_REC', NULL, '流程記錄', '流程運行時自動建立的記錄單', 0, TRUE, TRUE, TRUE, TRUE),
    ('SYS_CAT_OTHER', NULL, '其他', '未分類的表單和流程', 999, TRUE, TRUE, TRUE, TRUE)
ON CONFLICT (name, org_secure_code) DO NOTHING;

-- 更新現有表單和流程的預設分類
UPDATE fw_form_templates
SET category = '流程記錄'
WHERE category IS NULL OR category = '';

UPDATE fw_workflow_templates
SET category = '流程記錄'
WHERE category IS NULL OR category = '';

-- 添加註解
COMMENT ON TABLE fw_categories IS '表單流程分類';
COMMENT ON COLUMN fw_categories.org_secure_code IS '所屬企業代碼，NULL 表示系統分類';
COMMENT ON COLUMN fw_categories.is_system IS '是否為系統內建分類（無法刪除）';
COMMENT ON COLUMN fw_categories.show_in_form_design IS '在表單設計器顯示';
COMMENT ON COLUMN fw_categories.show_in_workflow_design IS '在流程設計器顯示';
COMMENT ON COLUMN fw_categories.show_in_form_center IS '在表單中心顯示';
