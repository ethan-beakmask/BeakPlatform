-- 012: 權限政策組 + 節點權限模式
-- 每個子系統可建立多個權限政策組，節點可選擇 inherit/policy/custom 模式

-- 權限政策組
CREATE TABLE IF NOT EXISTS dc_permission_policy_groups (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    sub_system_secure_code VARCHAR(32) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_ppg_org ON dc_permission_policy_groups (org_secure_code);
CREATE INDEX IF NOT EXISTS idx_ppg_sub_system ON dc_permission_policy_groups (sub_system_secure_code);
CREATE INDEX IF NOT EXISTS idx_ppg_deleted ON dc_permission_policy_groups (is_deleted);

-- 權限政策組規則
CREATE TABLE IF NOT EXISTS dc_permission_policy_rules (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    policy_group_secure_code VARCHAR(32) NOT NULL,
    grant_type VARCHAR(20) NOT NULL,
    grant_target VARCHAR(100) NOT NULL,
    grant_target_name VARCHAR(200) DEFAULT '',
    include_children BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_ppr_org ON dc_permission_policy_rules (org_secure_code);
CREATE INDEX IF NOT EXISTS idx_ppr_policy_group ON dc_permission_policy_rules (policy_group_secure_code);
CREATE INDEX IF NOT EXISTS idx_ppr_deleted ON dc_permission_policy_rules (is_deleted);

-- 節點新增權限模式欄位
ALTER TABLE dc_site_map_nodes
    ADD COLUMN IF NOT EXISTS permission_mode VARCHAR(20) DEFAULT 'inherit';

ALTER TABLE dc_site_map_nodes
    ADD COLUMN IF NOT EXISTS permission_policy_secure_code VARCHAR(32) DEFAULT NULL;
