-- 024_audit_log.sql
-- 稽核日誌表

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),
    user_secure_code VARCHAR(32) REFERENCES users(secure_code),
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(100),
    details TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_audit_logs_org ON audit_logs(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_secure_code);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at DESC);

-- 欄位註解
COMMENT ON TABLE audit_logs IS '稽核日誌';
COMMENT ON COLUMN audit_logs.org_secure_code IS '所屬企業';
COMMENT ON COLUMN audit_logs.user_secure_code IS '操作者';
COMMENT ON COLUMN audit_logs.action IS '操作類型 (CREATE, UPDATE, DELETE, TOGGLE_STATUS, etc.)';
COMMENT ON COLUMN audit_logs.resource_type IS '資源類型 (EXTERNAL_USER, USER, ROLE, etc.)';
COMMENT ON COLUMN audit_logs.resource_id IS '資源識別碼';
COMMENT ON COLUMN audit_logs.details IS '詳細描述';
COMMENT ON COLUMN audit_logs.ip_address IS '來源 IP';
COMMENT ON COLUMN audit_logs.user_agent IS '瀏覽器 User-Agent';

SELECT '稽核日誌表已建立' AS message;
