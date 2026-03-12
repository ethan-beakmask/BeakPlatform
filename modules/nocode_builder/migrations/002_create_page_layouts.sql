-- Data CRUD Module - 002: Create Page Layouts
-- dc_page_layouts: 頁面佈局配置（Web Builder）

CREATE TABLE IF NOT EXISTS dc_page_layouts (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    layout_json JSONB NOT NULL DEFAULT '{"widgets":[],"bindings":[]}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dc_page_layouts_org ON dc_page_layouts(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_page_layouts_secure_code ON dc_page_layouts(secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_page_layouts_is_active ON dc_page_layouts(is_active);
CREATE INDEX IF NOT EXISTS idx_dc_page_layouts_is_deleted ON dc_page_layouts(is_deleted);
