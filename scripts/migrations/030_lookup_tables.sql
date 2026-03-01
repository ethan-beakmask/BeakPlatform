-- Migration 030: Lookup Tables (通用選項清單)
-- 建立 lookup_categories 和 lookup_items 兩張表
-- org_secure_code nullable: NULL = 系統級, 有值 = 企業級

BEGIN;

-- ============================================================
-- lookup_categories: 類別定義
-- ============================================================
CREATE TABLE IF NOT EXISTS lookup_categories (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) REFERENCES organizations(secure_code),
    code VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    name_i18n JSONB DEFAULT '{}',
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    is_hierarchical BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- code 在同一 org 內唯一 (含 NULL)
CREATE UNIQUE INDEX IF NOT EXISTS uix_lookup_categories_org_code
    ON lookup_categories (COALESCE(org_secure_code, '__SYSTEM__'), code)
    WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS ix_lookup_categories_org
    ON lookup_categories (org_secure_code);

CREATE INDEX IF NOT EXISTS ix_lookup_categories_code
    ON lookup_categories (code);

CREATE INDEX IF NOT EXISTS ix_lookup_categories_secure_code
    ON lookup_categories (secure_code);

CREATE INDEX IF NOT EXISTS ix_lookup_categories_is_deleted
    ON lookup_categories (is_deleted);

COMMENT ON TABLE lookup_categories IS '通用選項清單 - 類別定義';
COMMENT ON COLUMN lookup_categories.org_secure_code IS 'NULL=系統級, 有值=企業級';
COMMENT ON COLUMN lookup_categories.code IS '類別代碼, 同一 org 內唯一';
COMMENT ON COLUMN lookup_categories.is_system IS '平台內建類別, 企業不可刪改';
COMMENT ON COLUMN lookup_categories.is_hierarchical IS '是否支援父子選項';

-- ============================================================
-- lookup_items: 選項資料
-- ============================================================
CREATE TABLE IF NOT EXISTS lookup_items (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) REFERENCES organizations(secure_code),
    category_code VARCHAR(100) NOT NULL,
    code VARCHAR(100) NOT NULL,
    label VARCHAR(200) NOT NULL,
    label_i18n JSONB DEFAULT '{}',
    value JSONB,
    parent_code VARCHAR(100),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- code 在同一 org + category 內唯一
CREATE UNIQUE INDEX IF NOT EXISTS uix_lookup_items_org_cat_code
    ON lookup_items (COALESCE(org_secure_code, '__SYSTEM__'), category_code, code)
    WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS ix_lookup_items_org
    ON lookup_items (org_secure_code);

CREATE INDEX IF NOT EXISTS ix_lookup_items_category_code
    ON lookup_items (category_code);

CREATE INDEX IF NOT EXISTS ix_lookup_items_parent_code
    ON lookup_items (parent_code);

CREATE INDEX IF NOT EXISTS ix_lookup_items_secure_code
    ON lookup_items (secure_code);

CREATE INDEX IF NOT EXISTS ix_lookup_items_is_deleted
    ON lookup_items (is_deleted);

CREATE INDEX IF NOT EXISTS ix_lookup_items_sort_order
    ON lookup_items (sort_order);

COMMENT ON TABLE lookup_items IS '通用選項清單 - 選項資料';
COMMENT ON COLUMN lookup_items.org_secure_code IS 'NULL=系統級, 有值=企業級';
COMMENT ON COLUMN lookup_items.category_code IS '所屬類別代碼';
COMMENT ON COLUMN lookup_items.code IS '選項代碼, 同一 org+category 內唯一';
COMMENT ON COLUMN lookup_items.label IS '顯示標籤 (zh-TW)';
COMMENT ON COLUMN lookup_items.label_i18n IS '多語系標籤 JSONB';
COMMENT ON COLUMN lookup_items.value IS '附加資料 JSONB (可選)';
COMMENT ON COLUMN lookup_items.parent_code IS '父選項代碼 (階層用)';
COMMENT ON COLUMN lookup_items.sort_order IS '排序順序';

-- ============================================================
-- RLS 政策
-- ============================================================

-- lookup_categories RLS
ALTER TABLE lookup_categories ENABLE ROW LEVEL SECURITY;

CREATE POLICY lookup_categories_select ON lookup_categories
    FOR SELECT
    USING (
        current_setting('app.is_system_admin', true) = 'true'
        OR org_secure_code IS NULL
        OR org_secure_code = current_setting('app.current_org', true)
    );

CREATE POLICY lookup_categories_insert ON lookup_categories
    FOR INSERT
    WITH CHECK (
        (current_setting('app.is_system_admin', true) = 'true')
        OR (org_secure_code IS NOT NULL AND org_secure_code = current_setting('app.current_org', true))
    );

CREATE POLICY lookup_categories_update ON lookup_categories
    FOR UPDATE
    USING (
        (current_setting('app.is_system_admin', true) = 'true')
        OR (org_secure_code IS NOT NULL AND org_secure_code = current_setting('app.current_org', true))
    );

CREATE POLICY lookup_categories_delete ON lookup_categories
    FOR DELETE
    USING (
        (current_setting('app.is_system_admin', true) = 'true')
        OR (org_secure_code IS NOT NULL AND org_secure_code = current_setting('app.current_org', true))
    );

-- lookup_items RLS
ALTER TABLE lookup_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY lookup_items_select ON lookup_items
    FOR SELECT
    USING (
        current_setting('app.is_system_admin', true) = 'true'
        OR org_secure_code IS NULL
        OR org_secure_code = current_setting('app.current_org', true)
    );

CREATE POLICY lookup_items_insert ON lookup_items
    FOR INSERT
    WITH CHECK (
        (current_setting('app.is_system_admin', true) = 'true')
        OR (org_secure_code IS NOT NULL AND org_secure_code = current_setting('app.current_org', true))
    );

CREATE POLICY lookup_items_update ON lookup_items
    FOR UPDATE
    USING (
        (current_setting('app.is_system_admin', true) = 'true')
        OR (org_secure_code IS NOT NULL AND org_secure_code = current_setting('app.current_org', true))
    );

CREATE POLICY lookup_items_delete ON lookup_items
    FOR DELETE
    USING (
        (current_setting('app.is_system_admin', true) = 'true')
        OR (org_secure_code IS NOT NULL AND org_secure_code = current_setting('app.current_org', true))
    );

-- ============================================================
-- 權限授予
-- ============================================================
GRANT SELECT, INSERT, UPDATE, DELETE ON lookup_categories TO beakplatform;
GRANT SELECT, INSERT, UPDATE, DELETE ON lookup_items TO beakplatform;
GRANT USAGE, SELECT ON SEQUENCE lookup_categories_id_seq TO beakplatform;
GRANT USAGE, SELECT ON SEQUENCE lookup_items_id_seq TO beakplatform;

COMMIT;
