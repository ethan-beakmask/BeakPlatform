-- Migration 014: 建立者/編輯者欄位 + 配對權限表
-- 2026-04-05

-- ============================================================
-- A. fw_form_templates 加入建立者/編輯者欄位
-- ============================================================
ALTER TABLE fw_form_templates
    ADD COLUMN IF NOT EXISTS created_by_secure_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS created_by_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS updated_by_secure_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS updated_by_name VARCHAR(100);

-- ============================================================
-- B. fw_workflow_templates 加入建立者/編輯者欄位
-- ============================================================
ALTER TABLE fw_workflow_templates
    ADD COLUMN IF NOT EXISTS created_by_secure_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS created_by_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS updated_by_secure_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS updated_by_name VARCHAR(100);

-- ============================================================
-- C. 新建配對權限表 fw_mapping_permissions
-- ============================================================
CREATE TABLE IF NOT EXISTS fw_mapping_permissions (
    id BIGSERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    mapping_secure_code VARCHAR(32) NOT NULL,
    grant_type VARCHAR(20) NOT NULL,
    grant_target VARCHAR(100) NOT NULL,
    grant_target_name VARCHAR(200) NOT NULL DEFAULT '',
    include_children BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    created_by_name VARCHAR(100),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP WITHOUT TIME ZONE,

    CONSTRAINT fw_mp_valid_grant_type CHECK (grant_type IN ('department', 'group', 'user'))
);

CREATE INDEX IF NOT EXISTS idx_fw_mp_org ON fw_mapping_permissions (org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_mp_mapping ON fw_mapping_permissions (mapping_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_mp_grant ON fw_mapping_permissions (grant_type, grant_target);

-- ============================================================
-- D. 回填既有資料的建立者（用 owner_secure_code 回填）
-- ============================================================
-- 備註：owner_secure_code 已有紀錄，但無姓名，先設定 secure_code，姓名留空
UPDATE fw_form_templates
SET created_by_secure_code = owner_secure_code,
    updated_by_secure_code = owner_secure_code
WHERE owner_secure_code IS NOT NULL
  AND created_by_secure_code IS NULL;

UPDATE fw_workflow_templates
SET created_by_secure_code = owner_secure_code,
    updated_by_secure_code = owner_secure_code
WHERE owner_secure_code IS NOT NULL
  AND created_by_secure_code IS NULL;
