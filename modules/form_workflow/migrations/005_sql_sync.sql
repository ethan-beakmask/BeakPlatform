-- ============================================================
-- 005: SQL Sync — 新增 SQL 同步功能所需的表和欄位
-- ============================================================

-- 1. fw_form_workflow_mappings: 加入 sql_sync_enabled 欄位
ALTER TABLE fw_form_workflow_mappings
    ADD COLUMN IF NOT EXISTS sql_sync_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. fw_sql_form_registries: SQL 同步登記表
CREATE TABLE IF NOT EXISTS fw_sql_form_registries (
    id BIGSERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,

    org_secure_code VARCHAR(100) NOT NULL,
    mapping_secure_code VARCHAR(32) NOT NULL,
    published_secure_code VARCHAR(32) NOT NULL,
    form_template_secure_code VARCHAR(32) NOT NULL,

    table_name VARCHAR(200) NOT NULL UNIQUE,
    form_version VARCHAR(10),
    publish_version INTEGER,

    column_mapping JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    row_count INTEGER DEFAULT 0,
    last_synced_at TIMESTAMP,
    create_ddl TEXT
);

CREATE INDEX IF NOT EXISTS idx_fw_sql_registry_org ON fw_sql_form_registries(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_sql_registry_mapping ON fw_sql_form_registries(mapping_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_sql_registry_published ON fw_sql_form_registries(published_secure_code);
