-- BeakPlatform: RBAC 出廠預設值表
-- 用途: 系統管理員儲存角色權限快照，供恢復預設值功能使用
-- 建立日期: 2026-04-01

CREATE TABLE IF NOT EXISTS rbac_defaults (
    id                SERIAL PRIMARY KEY,
    role_code         VARCHAR(50)  NOT NULL,
    permission_code   VARCHAR(50)  NOT NULL,
    saved_by          VARCHAR(100) NOT NULL,
    saved_at          TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_rbac_default_role_perm UNIQUE (role_code, permission_code)
);

CREATE INDEX IF NOT EXISTS idx_rbac_defaults_role ON rbac_defaults (role_code);
CREATE INDEX IF NOT EXISTS idx_rbac_defaults_perm ON rbac_defaults (permission_code);

COMMENT ON TABLE rbac_defaults IS 'RBAC 出廠預設值 - 系統管理員儲存的角色權限快照';
COMMENT ON COLUMN rbac_defaults.role_code IS '角色代碼 (對應 roles.code)';
COMMENT ON COLUMN rbac_defaults.permission_code IS '權限代碼 (對應 permissions.code)';
