-- 031_module_access_control.sql
-- 模組使用權控制表
-- 控制企業內「誰能使用哪個模組」，支援指派到角色/部門/群組/帳號

BEGIN;

CREATE TABLE IF NOT EXISTS module_access_control (
    id              SERIAL PRIMARY KEY,
    secure_code     VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),
    module_code     VARCHAR(100) NOT NULL,
    target_type     VARCHAR(20) NOT NULL CHECK (target_type IN ('ROLE', 'DEPARTMENT', 'GROUP', 'ACCOUNT')),
    target_secure_code VARCHAR(32) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at      TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_mac_org ON module_access_control(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_mac_module ON module_access_control(module_code);
CREATE INDEX IF NOT EXISTS idx_mac_deleted ON module_access_control(is_deleted);

-- 部分唯一索引: 同一企業、同一模組、同一目標不可重複指派
CREATE UNIQUE INDEX IF NOT EXISTS uq_mac_org_module_target
    ON module_access_control(org_secure_code, module_code, target_type, target_secure_code)
    WHERE is_deleted = FALSE;

-- 授權給應用程式帳號
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE module_access_control TO beakplatform;
GRANT USAGE, SELECT ON SEQUENCE module_access_control_id_seq TO beakplatform;

COMMIT;
