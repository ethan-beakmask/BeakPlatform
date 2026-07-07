-- 077: 平台級 API Key(外部系統 HMAC 認證)
-- 規格: docs/API_KEY_TRIGGER_SPEC.md
-- secret 用 Org Key 加密儲存(同 od_intake_keys 五欄位模式)

BEGIN;

CREATE TABLE IF NOT EXISTS api_keys (
    id                          SERIAL       PRIMARY KEY,
    secure_code                 VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code             VARCHAR(32)  NOT NULL,

    key_id                      VARCHAR(40)  UNIQUE NOT NULL,
    name                        VARCHAR(200) NOT NULL,
    consumer_label              VARCHAR(200) NULL,
    description                 VARCHAR(500) NULL,

    secret_ciphertext           BYTEA        NOT NULL,
    secret_file_nonce           BYTEA        NOT NULL,
    secret_wrapped_dek          VARCHAR(255) NOT NULL,
    secret_dek_nonce            VARCHAR(64)  NOT NULL,
    secret_encryption_key_sc    VARCHAR(32)  NOT NULL,

    status                      VARCHAR(20)  NOT NULL DEFAULT 'active',
    suspended_reason            VARCHAR(500) NULL,
    suspended_at                TIMESTAMP    NULL,

    allowed_ips                 JSONB        NULL,
    scopes                      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    applicant_user_secure_code  VARCHAR(32)  NULL,

    expires_at                  TIMESTAMP    NULL,
    last_used_at                TIMESTAMP    NULL,

    created_by_secure_code      VARCHAR(32)  NULL,
    created_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted                  BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at                  TIMESTAMP    NULL
);

CREATE INDEX IF NOT EXISTS idx_api_keys_org     ON api_keys(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_api_keys_keyid   ON api_keys(key_id) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_api_keys_status  ON api_keys(status);
CREATE INDEX IF NOT EXISTS idx_api_keys_deleted ON api_keys(is_deleted);

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_api_keys_tenant ON api_keys;
CREATE POLICY p_api_keys_tenant ON api_keys
    USING (org_secure_code = current_setting('app.current_org', true));

COMMENT ON TABLE  api_keys IS '平台級外部系統 API Key(HMAC,Org Key 加密儲存)';
COMMENT ON COLUMN api_keys.key_id IS '對外公開識別碼(放 X-BP-Key-Id header)';
COMMENT ON COLUMN api_keys.status IS 'active / suspended(可復原) / revoked(不可復原)';
COMMENT ON COLUMN api_keys.allowed_ips IS '來源 IP 白名單(含 CIDR);NULL = 不鎖';
COMMENT ON COLUMN api_keys.scopes IS '授權範圍 JSONB,消費端自行解釋(如 form_category/form)';
COMMENT ON COLUMN api_keys.applicant_user_secure_code IS '綁定的專用系統帳號,發動表單時的申請人';

COMMIT;
