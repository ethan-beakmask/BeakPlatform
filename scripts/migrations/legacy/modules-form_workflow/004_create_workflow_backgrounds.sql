-- FormWorkflow Module Migration: 建立流程設計器底圖表
-- 執行時間: 2026-01-28

-- 建立底圖表
CREATE TABLE IF NOT EXISTS fw_workflow_backgrounds (
    id BIGSERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,

    -- 檔案資訊
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    filepath VARCHAR(500) NOT NULL,
    filesize INTEGER,
    mimetype VARCHAR(100),

    -- 圖片尺寸
    width INTEGER,
    height INTEGER,

    -- 描述
    description VARCHAR(500),

    -- 時間戳記
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- 建立索引
CREATE INDEX IF NOT EXISTS idx_fw_workflow_backgrounds_org ON fw_workflow_backgrounds(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_backgrounds_deleted ON fw_workflow_backgrounds(is_deleted);

-- 添加註解
COMMENT ON TABLE fw_workflow_backgrounds IS '流程設計器底圖';
COMMENT ON COLUMN fw_workflow_backgrounds.filename IS '儲存的檔名（UUID）';
COMMENT ON COLUMN fw_workflow_backgrounds.original_filename IS '原始檔名';
COMMENT ON COLUMN fw_workflow_backgrounds.filepath IS '檔案儲存路徑';
