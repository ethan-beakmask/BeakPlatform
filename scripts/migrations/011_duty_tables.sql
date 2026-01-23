-- Migration: 011_duty_tables.sql
-- Description: 職務管理表 (Duty Management)
-- Author: Claude Code
-- Date: 2025-12-26

-- 職務分類表
CREATE TABLE IF NOT EXISTS duty_categories (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    deleted_at TIMESTAMP,

    CONSTRAINT uq_duty_category_code UNIQUE (org_secure_code, code)
);

-- 職務表
CREATE TABLE IF NOT EXISTS duties (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    unit_secure_code VARCHAR(32) NOT NULL REFERENCES organizational_units(secure_code),
    category_secure_code VARCHAR(32) NOT NULL REFERENCES duty_categories(secure_code),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    deleted_at TIMESTAMP,

    -- 唯一約束：部門 + 分類 + 名稱
    CONSTRAINT uq_duty_unit_category_name UNIQUE (unit_secure_code, category_secure_code, name)
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_duty_categories_org ON duty_categories(org_secure_code);
CREATE INDEX IF NOT EXISTS ix_duty_categories_is_deleted ON duty_categories(is_deleted);

CREATE INDEX IF NOT EXISTS ix_duties_org ON duties(org_secure_code);
CREATE INDEX IF NOT EXISTS ix_duties_unit ON duties(unit_secure_code);
CREATE INDEX IF NOT EXISTS ix_duties_category ON duties(category_secure_code);
CREATE INDEX IF NOT EXISTS ix_duties_is_deleted ON duties(is_deleted);

-- 欄位註解
COMMENT ON TABLE duty_categories IS '職務分類表';
COMMENT ON COLUMN duty_categories.code IS '分類代碼（組織內唯一）';
COMMENT ON COLUMN duty_categories.name IS '分類名稱';
COMMENT ON COLUMN duty_categories.description IS '分類描述';

COMMENT ON TABLE duties IS '職務表（部門職責標籤）';
COMMENT ON COLUMN duties.unit_secure_code IS '所屬部門';
COMMENT ON COLUMN duties.category_secure_code IS '職務分類';
COMMENT ON COLUMN duties.name IS '職務名稱';
COMMENT ON COLUMN duties.description IS '職務描述';
