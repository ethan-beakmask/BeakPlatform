-- 115: API Key one-time claims and ApiKeyIssue workflow node

BEGIN;

CREATE TABLE IF NOT EXISTS api_key_claims (
    id                              SERIAL      PRIMARY KEY,
    secure_code                     VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code                 VARCHAR(32) NOT NULL,
    api_key_secure_code             VARCHAR(32) NOT NULL,
    beneficiary_user_secure_code    VARCHAR(32) NOT NULL,
    form_instance_secure_code       VARCHAR(32) NULL,
    expires_at                      TIMESTAMP   NOT NULL,
    claimed_at                      TIMESTAMP   NULL,
    claimed_ip                      VARCHAR(45) NULL,
    created_at                      TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at                      TIMESTAMP   NOT NULL DEFAULT NOW(),
    is_deleted                      BOOLEAN     NOT NULL DEFAULT FALSE,
    deleted_at                      TIMESTAMP   NULL
);

CREATE INDEX IF NOT EXISTS idx_api_key_claims_org
    ON api_key_claims(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_api_key_claims_beneficiary
    ON api_key_claims(beneficiary_user_secure_code);
CREATE INDEX IF NOT EXISTS idx_api_key_claims_api_key
    ON api_key_claims(api_key_secure_code);
CREATE INDEX IF NOT EXISTS idx_api_key_claims_deleted
    ON api_key_claims(is_deleted);

COMMENT ON TABLE api_key_claims IS 'API Key 一次性領取憑證；不儲存 secret 明文、密文或雜湊';

INSERT INTO workflow_node_definitions (
    secure_code,
    node_type,
    scope,
    org_secure_code,
    category,
    display_name,
    description,
    icon,
    execution_handler,
    config_schema,
    canvas_shape,
    canvas_color,
    canvas_width,
    canvas_height,
    max_input_connections,
    max_output_connections,
    default_timeout_seconds,
    max_timeout_seconds,
    require_system_admin,
    is_active,
    is_deleted,
    created_at,
    updated_at
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    'ApiKeyIssue',
    'SYSTEM',
    NULL,
    '安全',
    'API Key 核發',
    '依核准後的申請單建立平台 API Key，並產生一次性領取憑證；secret 不寫入流程變數或節點結果。',
    (SELECT icon FROM workflow_node_definitions
     WHERE node_type = 'ApiKeyAction' LIMIT 1),
    'modules.form_workflow.services.node_handlers.api_key_issue_handler.ApiKeyIssueHandler',
    '{
        "beneficiary_field": "string",
        "forms_field": "string",
        "purpose_field": "string",
        "expires_field": "string",
        "allowed_ips_field": "string",
        "claim_ttl_hours": "integer",
        "result_var": "string"
    }'::jsonb,
    'roundrectangle',
    '#DC2626',
    140,
    60,
    -1,
    -1,
    60,
    600,
    FALSE,
    TRUE,
    FALSE,
    NOW(),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM workflow_node_definitions WHERE node_type = 'ApiKeyIssue'
);

COMMIT;
