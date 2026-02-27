-- Data CRUD Module - 001: Create Tables
-- dc_crud_views: CRUD 視圖配置

CREATE TABLE IF NOT EXISTS dc_crud_views (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    table_name VARCHAR(128) NOT NULL,
    columns_config JSONB NOT NULL DEFAULT '[]'::jsonb,
    allow_create BOOLEAN NOT NULL DEFAULT TRUE,
    allow_edit BOOLEAN NOT NULL DEFAULT TRUE,
    allow_delete BOOLEAN NOT NULL DEFAULT TRUE,
    soft_delete_column VARCHAR(128),
    default_sort_column VARCHAR(128),
    default_sort_dir VARCHAR(4) NOT NULL DEFAULT 'ASC',
    page_size INTEGER NOT NULL DEFAULT 20,
    fixed_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dc_crud_views_org ON dc_crud_views(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_crud_views_secure_code ON dc_crud_views(secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_crud_views_is_active ON dc_crud_views(is_active);
CREATE INDEX IF NOT EXISTS idx_dc_crud_views_is_deleted ON dc_crud_views(is_deleted);
