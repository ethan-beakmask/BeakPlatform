-- 073: OpenDefense 模組建表
-- 建立日期: 2026-05-09
-- 對外契約: docs/integrations/open_defense_contract.md (v1.0)
--
-- 5 張表:
--   od_intake_keys              事件接收金鑰(HMAC,Org Key 加密儲存)
--   od_intake_events            收到的事件(冪等 + 稽核)
--   od_defense_decisions        防禦決策(供外部執行端拉取)
--   od_service_accounts         執行端帳號(bcrypt 雜湊)
--   od_form_template_mappings   event_class -> form_template 對應
--
-- 所有表啟用 RLS,policy 依 current_setting('app.current_org', true) 過濾。

BEGIN;

-- =============================================================================
-- 1. od_intake_keys
-- =============================================================================
CREATE TABLE IF NOT EXISTS od_intake_keys (
    id                              SERIAL       PRIMARY KEY,
    secure_code                     VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code                 VARCHAR(32)  NOT NULL,

    key_id                          VARCHAR(40)  UNIQUE NOT NULL,
    name                            VARCHAR(200) NOT NULL,

    hmac_secret_ciphertext          BYTEA        NOT NULL,
    hmac_secret_file_nonce          BYTEA        NOT NULL,
    hmac_secret_wrapped_dek         VARCHAR(255) NOT NULL,
    hmac_secret_dek_nonce           VARCHAR(64)  NOT NULL,
    hmac_secret_encryption_key_sc   VARCHAR(32)  NOT NULL,

    allowed_source_systems          JSONB        NOT NULL DEFAULT '[]'::jsonb,

    is_active                       BOOLEAN      NOT NULL DEFAULT TRUE,
    expires_at                      TIMESTAMP    NULL,
    last_used_at                    TIMESTAMP    NULL,

    created_by_secure_code          VARCHAR(32)  NULL,
    created_at                      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at                      TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted                      BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at                      TIMESTAMP    NULL
);

CREATE INDEX IF NOT EXISTS idx_od_intake_keys_org      ON od_intake_keys(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_od_intake_keys_keyid    ON od_intake_keys(key_id) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_od_intake_keys_deleted  ON od_intake_keys(is_deleted);

ALTER TABLE od_intake_keys ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_od_intake_keys_tenant ON od_intake_keys;
CREATE POLICY p_od_intake_keys_tenant ON od_intake_keys
    USING (org_secure_code = current_setting('app.current_org', true));

COMMENT ON TABLE  od_intake_keys IS 'OpenDefense: 事件接收 HMAC 金鑰(Org Key 加密儲存)';
COMMENT ON COLUMN od_intake_keys.key_id IS '對外公開識別碼(放 X-OD-Key-Id header)';
COMMENT ON COLUMN od_intake_keys.allowed_source_systems IS '此 key 允許宣稱的 source_system 值清單';


-- =============================================================================
-- 2. od_intake_events  (相依 od_intake_keys.secure_code,但僅邏輯關聯,不建 FK)
-- =============================================================================
CREATE TABLE IF NOT EXISTS od_intake_events (
    id                          SERIAL       PRIMARY KEY,
    secure_code                 VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code             VARCHAR(32)  NOT NULL,

    correlation_id              VARCHAR(64)  NOT NULL,

    intake_key_secure_code      VARCHAR(32)  NOT NULL,

    source_system               VARCHAR(50)  NOT NULL,
    event_class                 VARCHAR(30)  NOT NULL,
    severity_id                 SMALLINT     NULL,

    raw_body                    JSONB        NOT NULL,
    signature_verified          BOOLEAN      NOT NULL DEFAULT FALSE,

    case_secure_code            VARCHAR(32)  NULL,

    received_at                 TIMESTAMP    NOT NULL,

    created_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted                  BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at                  TIMESTAMP    NULL,

    CONSTRAINT uq_od_intake_correlation UNIQUE (correlation_id)
);

CREATE INDEX IF NOT EXISTS idx_od_intake_events_org_received
    ON od_intake_events(org_secure_code, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_od_intake_events_intake_key
    ON od_intake_events(intake_key_secure_code);
CREATE INDEX IF NOT EXISTS idx_od_intake_events_case
    ON od_intake_events(case_secure_code) WHERE case_secure_code IS NOT NULL;

ALTER TABLE od_intake_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_od_intake_events_tenant ON od_intake_events;
CREATE POLICY p_od_intake_events_tenant ON od_intake_events
    USING (org_secure_code = current_setting('app.current_org', true));

COMMENT ON TABLE  od_intake_events IS 'OpenDefense: webhook 收到的 OCSF 事件(冪等 + 稽核)';
COMMENT ON COLUMN od_intake_events.correlation_id IS '對外冪等鍵,全表 UNIQUE';


-- =============================================================================
-- 3. od_defense_decisions
-- =============================================================================
CREATE TABLE IF NOT EXISTS od_defense_decisions (
    id                                  SERIAL       PRIMARY KEY,
    secure_code                         VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code                     VARCHAR(32)  NOT NULL,

    case_secure_code                    VARCHAR(32)  NULL,
    workflow_node_id                    VARCHAR(40)  NULL,
    intake_event_secure_code            VARCHAR(32)  NULL,

    action                              VARCHAR(20)  NOT NULL,
    target_type                         VARCHAR(20)  NOT NULL,
    target_value                        VARCHAR(500) NOT NULL,
    enforcement_points                  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    severity                            VARCHAR(10)  NULL,

    ttl_seconds                         INTEGER      NULL,
    expires_at                          TIMESTAMP    NULL,

    reason                              TEXT         NULL,
    decided_via                         VARCHAR(10)  NOT NULL,
    decided_by_secure_code              VARCHAR(32)  NULL,
    decided_at                          TIMESTAMP    NOT NULL,

    status                              VARCHAR(20)  NOT NULL DEFAULT 'pending',
    picked_up_at                        TIMESTAMP    NULL,
    applied_at                          TIMESTAMP    NULL,
    applied_by                          VARCHAR(100) NULL,
    application_result                  JSONB        NULL,
    error_message                       TEXT         NULL,

    revoked_by_decision_secure_code     VARCHAR(32)  NULL,

    related_finding_ids                 JSONB        NULL,
    decision_metadata                   JSONB        NULL,

    created_at                          TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at                          TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted                          BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at                          TIMESTAMP    NULL,

    CONSTRAINT chk_od_decision_action CHECK (action IN
        ('block','unblock','allow','escalate','observe')),
    CONSTRAINT chk_od_decision_target CHECK (target_type IN
        ('ip','ipv6','cidr','domain','url','asn','country','user_agent','jwt_sub')),
    CONSTRAINT chk_od_decision_via CHECK (decided_via IN
        ('human','auto','ai')),
    CONSTRAINT chk_od_decision_status CHECK (status IN
        ('pending','picked_up','applied','partial','failed','expired','revoked')),
    CONSTRAINT chk_od_decision_severity CHECK (severity IS NULL OR severity IN
        ('info','low','medium','high','critical'))
);

CREATE INDEX IF NOT EXISTS idx_od_decisions_pending_expiry
    ON od_defense_decisions(status, expires_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_od_decisions_target
    ON od_defense_decisions(target_type, target_value);
CREATE INDEX IF NOT EXISTS idx_od_decisions_org_time
    ON od_defense_decisions(org_secure_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_od_decisions_ep
    ON od_defense_decisions USING gin (enforcement_points);
CREATE INDEX IF NOT EXISTS idx_od_decisions_case
    ON od_defense_decisions(case_secure_code) WHERE case_secure_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_od_decisions_intake
    ON od_defense_decisions(intake_event_secure_code) WHERE intake_event_secure_code IS NOT NULL;

ALTER TABLE od_defense_decisions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_od_defense_decisions_tenant ON od_defense_decisions;
CREATE POLICY p_od_defense_decisions_tenant ON od_defense_decisions
    USING (org_secure_code = current_setting('app.current_org', true));

COMMENT ON TABLE od_defense_decisions IS
  'OpenDefense: 防禦決策廣播表(供外部執行端輪詢拉取後落地)';


-- =============================================================================
-- 4. od_service_accounts
-- =============================================================================
CREATE TABLE IF NOT EXISTS od_service_accounts (
    id                              SERIAL       PRIMARY KEY,
    secure_code                     VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code                 VARCHAR(32)  NOT NULL,

    sa_id                           VARCHAR(60)  UNIQUE NOT NULL,
    name                            VARCHAR(200) NOT NULL,

    secret_hash                     VARCHAR(255) NOT NULL,

    allowed_enforcement_points      JSONB        NOT NULL DEFAULT '[]'::jsonb,

    is_active                       BOOLEAN      NOT NULL DEFAULT TRUE,

    last_login_at                   TIMESTAMP    NULL,
    last_login_ip                   INET         NULL,

    failed_login_count              INTEGER      NOT NULL DEFAULT 0,
    lock_until                      TIMESTAMP    NULL,

    created_by_secure_code          VARCHAR(32)  NULL,
    created_at                      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at                      TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted                      BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at                      TIMESTAMP    NULL
);

CREATE INDEX IF NOT EXISTS idx_od_sa_org    ON od_service_accounts(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_od_sa_said   ON od_service_accounts(sa_id) WHERE is_deleted = FALSE;

ALTER TABLE od_service_accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_od_service_accounts_tenant ON od_service_accounts;
CREATE POLICY p_od_service_accounts_tenant ON od_service_accounts
    USING (org_secure_code = current_setting('app.current_org', true));

COMMENT ON TABLE  od_service_accounts IS 'OpenDefense: 執行端 Service Account(secret 採 bcrypt)';
COMMENT ON COLUMN od_service_accounts.secret_hash IS 'bcrypt(secret),不可解密';


-- =============================================================================
-- 5. od_form_template_mappings
-- =============================================================================
CREATE TABLE IF NOT EXISTS od_form_template_mappings (
    id                          SERIAL       PRIMARY KEY,
    secure_code                 VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code             VARCHAR(32)  NOT NULL,

    event_class                 VARCHAR(30)  NOT NULL,
    form_template_secure_code   VARCHAR(32)  NOT NULL,
    note                        VARCHAR(500) NULL,

    created_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted                  BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at                  TIMESTAMP    NULL,

    CONSTRAINT uq_od_template_map_org_event UNIQUE (org_secure_code, event_class)
);

CREATE INDEX IF NOT EXISTS idx_od_template_map_org ON od_form_template_mappings(org_secure_code);

ALTER TABLE od_form_template_mappings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_od_template_map_tenant ON od_form_template_mappings;
CREATE POLICY p_od_template_map_tenant ON od_form_template_mappings
    USING (org_secure_code = current_setting('app.current_org', true));

COMMENT ON TABLE od_form_template_mappings IS
  'OpenDefense: event_class -> form_template 對應(取代硬編 default)';


COMMIT;
