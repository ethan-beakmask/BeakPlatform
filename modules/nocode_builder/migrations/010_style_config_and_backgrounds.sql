-- 010: 頁面/子系統樣式設定 + 底圖圖庫
-- 2026-04-07

-- 子系統預設樣式
ALTER TABLE dc_sub_systems
    ADD COLUMN IF NOT EXISTS style_config JSONB NOT NULL DEFAULT '{}';

-- 頁面樣式（覆蓋子系統預設）
ALTER TABLE dc_page_layouts
    ADD COLUMN IF NOT EXISTS style_config JSONB NOT NULL DEFAULT '{}';

-- 底圖圖庫（參考 fw_workflow_backgrounds）
CREATE TABLE IF NOT EXISTS dc_backgrounds (
    id              BIGSERIAL PRIMARY KEY,
    secure_code     VARCHAR(32)  NOT NULL UNIQUE,
    org_secure_code VARCHAR(32)  NOT NULL,
    filename        VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    filepath        VARCHAR(500) NOT NULL,
    filesize        INTEGER,
    mimetype        VARCHAR(100),
    width           INTEGER,
    height          INTEGER,
    description     VARCHAR(500),
    platform_file_sc VARCHAR(32),
    created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at      TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_dc_backgrounds_org
    ON dc_backgrounds (org_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_backgrounds_deleted
    ON dc_backgrounds (is_deleted);
