-- Migration: 003_create_sub_systems
-- 建立子系統與子系統頁面表
-- 用途: Web Builder 子系統權限架構

-- 子系統表
CREATE TABLE IF NOT EXISTS dc_sub_systems (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    group_unit_secure_code VARCHAR(32) NOT NULL,
    menu_item_secure_code VARCHAR(32),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dc_sub_systems_org ON dc_sub_systems(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_sub_systems_group ON dc_sub_systems(group_unit_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_sub_systems_deleted ON dc_sub_systems(is_deleted);

-- 子系統頁面表
CREATE TABLE IF NOT EXISTS dc_sub_system_pages (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    sub_system_secure_code VARCHAR(32) NOT NULL,
    page_layout_secure_code VARCHAR(32) NOT NULL,
    display_name VARCHAR(200),
    display_order INTEGER NOT NULL DEFAULT 0,
    visible_roles JSONB NOT NULL DEFAULT '["*"]'::jsonb,
    crud_overrides JSONB DEFAULT '{}'::jsonb,
    data_filters JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dc_ssp_org ON dc_sub_system_pages(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_ssp_sub_system ON dc_sub_system_pages(sub_system_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_ssp_page ON dc_sub_system_pages(page_layout_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_ssp_deleted ON dc_sub_system_pages(is_deleted);
