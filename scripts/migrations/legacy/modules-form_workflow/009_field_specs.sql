-- 009_field_specs.sql
-- Schema-First Form Builder: 欄位規格定義 + 版本歷史
-- 建立日期: 2026-02-23

-- =============================================================================
-- 1. 欄位規格定義表
-- =============================================================================
CREATE TABLE IF NOT EXISTS fw_form_field_specs (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,

    -- 組織隔離
    org_secure_code VARCHAR(32) NOT NULL,

    -- 關聯表單模板
    form_template_secure_code VARCHAR(32) NOT NULL,

    -- 版本
    version INT NOT NULL DEFAULT 1,

    -- 欄位定義 (JSONB array)
    -- 每筆: {field_key, label, formio_type, pg_type, constraints, is_pii, description, default_value, options, grid_children, sort_order}
    fields JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- 狀態: active / archived
    status VARCHAR(20) NOT NULL DEFAULT 'active',

    -- 描述
    description TEXT,

    -- 修改者
    last_modified_by VARCHAR(32),
    last_modified_by_name VARCHAR(200),

    -- 時間戳記
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 軟刪除
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

-- 每個 form_template 最多一筆 active spec（partial unique index）
CREATE UNIQUE INDEX IF NOT EXISTS idx_fw_field_specs_active_unique
    ON fw_form_field_specs (org_secure_code, form_template_secure_code)
    WHERE status = 'active' AND is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_fw_field_specs_org
    ON fw_form_field_specs (org_secure_code);

CREATE INDEX IF NOT EXISTS idx_fw_field_specs_form_template
    ON fw_form_field_specs (form_template_secure_code);


-- =============================================================================
-- 2. 欄位規格版本歷史表
-- =============================================================================
CREATE TABLE IF NOT EXISTS fw_form_field_spec_histories (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,

    -- 組織隔離（繼承自 ModuleBaseModel）
    org_secure_code VARCHAR(32),

    -- 關聯 spec
    spec_secure_code VARCHAR(32) NOT NULL,

    -- 關聯表單模板（冗餘，方便查詢）
    form_template_secure_code VARCHAR(32) NOT NULL,

    -- 版本號（與 spec 對應）
    version INT NOT NULL,

    -- 欄位快照
    fields_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- 變更描述
    change_description TEXT,

    -- 變更差異 (JSON: {added: [...], modified: [...], removed: [...]})
    change_diff JSONB,

    -- 修改者
    changed_by VARCHAR(32),
    changed_by_name VARCHAR(200),

    -- 時間戳記
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 軟刪除
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fw_field_spec_histories_spec
    ON fw_form_field_spec_histories (spec_secure_code);

CREATE INDEX IF NOT EXISTS idx_fw_field_spec_histories_form_template
    ON fw_form_field_spec_histories (form_template_secure_code);

CREATE INDEX IF NOT EXISTS idx_fw_field_spec_histories_version
    ON fw_form_field_spec_histories (form_template_secure_code, version DESC);


-- =============================================================================
-- 3. 權限（beakplatform 用戶）
-- =============================================================================
GRANT ALL PRIVILEGES ON TABLE fw_form_field_specs TO beakplatform;
GRANT ALL PRIVILEGES ON TABLE fw_form_field_spec_histories TO beakplatform;
GRANT USAGE, SELECT ON SEQUENCE fw_form_field_specs_id_seq TO beakplatform;
GRANT USAGE, SELECT ON SEQUENCE fw_form_field_spec_histories_id_seq TO beakplatform;
