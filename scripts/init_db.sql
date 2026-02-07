-- BeakMask Database Initialization Script
-- Includes Row Level Security (RLS) for tenant isolation

-- =============================================================================
-- 1. CREATE EXTENSIONS
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 2. CREATE APPLICATION ROLE
-- =============================================================================
-- This role will be used by the application, with RLS enforced
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'beakmask_app') THEN
        CREATE ROLE beakmask_app WITH LOGIN PASSWORD 'app_password_change_me';
    END IF;
END
$$;

-- =============================================================================
-- 3. CREATE TABLES
-- =============================================================================

-- Organizations table (no RLS - it's the top level)
CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,
    settings TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_organizations_secure_code ON organizations(secure_code);
CREATE INDEX IF NOT EXISTS idx_organizations_code ON organizations(code);
CREATE INDEX IF NOT EXISTS idx_organizations_is_deleted ON organizations(is_deleted);

-- Users table (with RLS)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,
    is_org_admin BOOLEAN DEFAULT FALSE NOT NULL,
    is_system_admin BOOLEAN DEFAULT FALSE NOT NULL,
    last_login_at TIMESTAMP,
    preferences TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_secure_code ON users(secure_code);
CREATE INDEX IF NOT EXISTS idx_users_org_secure_code ON users(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_deleted ON users(is_deleted);

-- =============================================================================
-- 4. ROW LEVEL SECURITY (RLS)
-- =============================================================================

-- Enable RLS on users table
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see users in their own organization
-- The app sets current_setting('app.current_org') before queries
CREATE POLICY users_org_isolation ON users
    FOR ALL
    USING (
        -- System admins bypass (check via session variable)
        current_setting('app.is_system_admin', true) = 'true'
        OR
        -- Regular users: only see their org's data
        org_secure_code = current_setting('app.current_org', true)
    );

-- =============================================================================
-- 5. HELPER FUNCTIONS
-- =============================================================================

-- Function to set tenant context (called before each request)
CREATE OR REPLACE FUNCTION set_tenant_context(
    p_org_secure_code VARCHAR,
    p_is_system_admin BOOLEAN DEFAULT FALSE
) RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.current_org', COALESCE(p_org_secure_code, ''), true);
    PERFORM set_config('app.is_system_admin', p_is_system_admin::TEXT, true);
END;
$$ LANGUAGE plpgsql;

-- Function to clear tenant context (called after each request)
CREATE OR REPLACE FUNCTION clear_tenant_context() RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.current_org', '', true);
    PERFORM set_config('app.is_system_admin', 'false', true);
END;
$$ LANGUAGE plpgsql;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- 6. TRIGGERS
-- =============================================================================

-- Auto-update updated_at
CREATE TRIGGER update_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- 7. GRANT PERMISSIONS
-- =============================================================================

-- Grant permissions to app role
GRANT USAGE ON SCHEMA public TO beakmask_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO beakmask_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO beakmask_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO beakmask_app;

-- =============================================================================
-- 8. SEED DATA
-- =============================================================================
-- 注意: Seed 資料現在由 Python 腳本建立，以確保 secure_code 使用 token_urlsafe(16) 生成
-- 執行方式: python scripts/seed_data.py
--
-- 不要在此處硬編碼 secure_code！這會造成安全風險（可被猜測）

-- =============================================================================
-- 9. COMMENTS - 資料表註解
-- =============================================================================

COMMENT ON TABLE organizations IS '企業/租戶表 - 多租戶架構的頂層實體，所有資料都屬於某個企業';
COMMENT ON TABLE users IS '用戶帳號表 - 含 RLS 保護，自動隔離不同企業的用戶';
COMMENT ON FUNCTION set_tenant_context IS '設定當前租戶上下文，供 RLS 使用';
COMMENT ON FUNCTION clear_tenant_context IS '清除租戶上下文，請求結束時呼叫';

-- =============================================================================
-- organizations 欄位註解
-- =============================================================================
COMMENT ON COLUMN organizations.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN organizations.secure_code IS '外部識別碼 (32 字元)，對外暴露使用，取代自增 ID';
COMMENT ON COLUMN organizations.code IS '企業代碼，全系統唯一，用於 URL 和識別';
COMMENT ON COLUMN organizations.name IS '企業名稱';
COMMENT ON COLUMN organizations.description IS '企業描述';
COMMENT ON COLUMN organizations.is_active IS '是否啟用，FALSE 時該企業所有用戶無法登入';
COMMENT ON COLUMN organizations.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN organizations.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN organizations.settings IS '企業設定 (JSON 格式)';
COMMENT ON COLUMN organizations.created_at IS '建立時間';
COMMENT ON COLUMN organizations.updated_at IS '最後更新時間';

-- =============================================================================
-- users 欄位註解
-- =============================================================================
COMMENT ON COLUMN users.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN users.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN users.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN users.email IS '電子郵件，全系統唯一，用於登入';
COMMENT ON COLUMN users.password_hash IS '密碼雜湊 (bcrypt)，永不儲存明文密碼';
COMMENT ON COLUMN users.display_name IS '顯示名稱，用於 UI 顯示';
COMMENT ON COLUMN users.is_active IS '是否啟用，FALSE 時無法登入';
COMMENT ON COLUMN users.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN users.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN users.is_org_admin IS '是否為企業管理員，可管理該企業所有用戶';
COMMENT ON COLUMN users.is_system_admin IS '是否為系統管理員，可管理所有企業';
COMMENT ON COLUMN users.last_login_at IS '最後登入時間';
COMMENT ON COLUMN users.preferences IS '用戶偏好設定 (JSON 格式)';
COMMENT ON COLUMN users.created_at IS '建立時間';
COMMENT ON COLUMN users.updated_at IS '最後更新時間';

-- =============================================================================
-- SECURITY NOTES:
--
-- 1. RLS is the last line of defense - application should also filter by org
-- 2. System admins bypass RLS via app.is_system_admin setting
-- 3. Always call set_tenant_context() at the start of each request
-- 4. Always call clear_tenant_context() at the end of each request
-- 5. Default admin password MUST be changed in production
-- =============================================================================
