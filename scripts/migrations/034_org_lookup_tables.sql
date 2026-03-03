-- ============================================================================
-- 034_org_lookup_tables.sql
-- 企業 DB lookup 表結構 (參考用 DDL，不在主庫執行)
--
-- 此 DDL 由 LookupOrgService.ensure_tables() 懶建表機制自動執行，
-- 放在此處僅供文件參考。
-- ============================================================================

-- 在企業專屬資料庫 (org_{id}) 中執行:

CREATE TABLE IF NOT EXISTS lookup_categories (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    name_i18n JSONB DEFAULT '{}',
    description TEXT,
    is_hierarchical BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_org_lkcat_code
    ON lookup_categories (code) WHERE is_deleted = FALSE;


CREATE TABLE IF NOT EXISTS lookup_items (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
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

CREATE UNIQUE INDEX IF NOT EXISTS uix_org_lkitem_cat_code
    ON lookup_items (category_code, code) WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS ix_org_lkitem_category_code
    ON lookup_items (category_code);


-- GRANT 給 sync 角色 (bfsync_{org_id}):
-- GRANT SELECT, INSERT, UPDATE, DELETE ON lookup_categories, lookup_items TO {sync_user};
-- GRANT USAGE, SELECT ON SEQUENCE lookup_categories_id_seq, lookup_items_id_seq TO {sync_user};
