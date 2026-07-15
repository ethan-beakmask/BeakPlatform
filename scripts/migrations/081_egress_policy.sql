-- 081: 資料出口政策（欄位能見度 + 計量閾值 + 出口稽核）
-- 規格: docs/EGRESS_POLICY_SPEC.md

BEGIN;

CREATE TABLE IF NOT EXISTS egress_field_policies (
    id                      SERIAL       PRIMARY KEY,
    secure_code             VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code         VARCHAR(32)  NOT NULL REFERENCES organizations(secure_code),

    resource_code           VARCHAR(50)  NOT NULL,
    field_name              VARCHAR(100) NOT NULL,
    context                 VARCHAR(20)  NOT NULL,  -- list/detail/form_node/export

    role_secure_code        VARCHAR(32)  NULL,      -- NULL = 資源預設政策
    department_secure_code  VARCHAR(32)  NULL,      -- NULL = 該角色全部門
    node_key                VARCHAR(100) NULL,      -- form_node 語境的節點綁定

    visibility              VARCHAR(10)  NOT NULL DEFAULT 'clear',  -- clear/masked/hidden
    tier                    VARCHAR(20)  NOT NULL DEFAULT 'normal',
    is_active               BOOLEAN      NOT NULL DEFAULT TRUE,

    created_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted              BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at              TIMESTAMP    NULL,

    CONSTRAINT uq_egress_policy_scope UNIQUE (
        org_secure_code, resource_code, field_name, context,
        role_secure_code, department_secure_code, node_key
    )
);
CREATE INDEX IF NOT EXISTS idx_egress_policies_lookup
    ON egress_field_policies (org_secure_code, resource_code, context)
    WHERE is_deleted = FALSE AND is_active = TRUE;

CREATE TABLE IF NOT EXISTS egress_tier_thresholds (
    id                      SERIAL       PRIMARY KEY,
    secure_code             VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code         VARCHAR(32)  NOT NULL REFERENCES organizations(secure_code),

    tier                    VARCHAR(20)  NOT NULL,
    meter                   VARCHAR(20)  NOT NULL,  -- list_rows/reveal/export
    threshold               INTEGER      NOT NULL,
    window_minutes          INTEGER      NOT NULL DEFAULT 60,
    is_active               BOOLEAN      NOT NULL DEFAULT TRUE,

    created_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted              BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at              TIMESTAMP    NULL,

    CONSTRAINT uq_egress_threshold_scope UNIQUE (org_secure_code, tier, meter)
);

CREATE TABLE IF NOT EXISTS egress_audit_logs (
    id                      SERIAL       PRIMARY KEY,
    secure_code             VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code         VARCHAR(32)  NOT NULL REFERENCES organizations(secure_code),

    user_secure_code        VARCHAR(32)  NOT NULL,
    resource_code           VARCHAR(50)  NOT NULL,
    context                 VARCHAR(20)  NOT NULL,
    action                  VARCHAR(20)  NOT NULL,  -- list/detail/reveal/export/alert
    record_scs              JSONB        NULL,
    field_name              VARCHAR(100) NULL,
    row_count               INTEGER      NOT NULL DEFAULT 0,
    tier                    VARCHAR(20)  NULL,
    meter                   VARCHAR(20)  NULL,
    ip_address              VARCHAR(45)  NULL,

    created_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted              BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at              TIMESTAMP    NULL
);
-- 水表滑動窗查詢用
CREATE INDEX IF NOT EXISTS idx_egress_audit_meter
    ON egress_audit_logs (org_secure_code, user_secure_code, tier, action, created_at);
CREATE INDEX IF NOT EXISTS idx_egress_audit_resource
    ON egress_audit_logs (org_secure_code, resource_code, created_at);

COMMIT;
