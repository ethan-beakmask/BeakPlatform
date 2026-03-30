-- BeakMask Migration: 002_organization_contracts
-- 企業客戶與合約管理系統
-- 執行日期: 2025-12-19

-- ============================================
-- 1. 更新 organizations 表
-- ============================================

-- 新增欄位
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS domain_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS customer_type VARCHAR(20) DEFAULT 'TRIAL',
    ADD COLUMN IF NOT EXISTS user_limit INTEGER DEFAULT 50,
    ADD COLUMN IF NOT EXISTS contact_person VARCHAR(100),
    ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(50),
    ADD COLUMN IF NOT EXISTS address TEXT;

-- 設定 domain_name 預設值 (用現有的 code)
UPDATE organizations
SET domain_name = LOWER(code) || '.local'
WHERE domain_name IS NULL;

-- 設定 domain_name 為必填且唯一
ALTER TABLE organizations
    ALTER COLUMN domain_name SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_domain_name
    ON organizations(domain_name) WHERE is_deleted = FALSE;

-- ============================================
-- 2. 建立 contracts 表
-- ============================================

CREATE TABLE IF NOT EXISTS contracts (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code) ON UPDATE CASCADE,

    contract_number VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255),
    description TEXT,

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    amount NUMERIC(12, 2),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

    modules_config TEXT,
    notes TEXT,

    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contracts_org ON contracts(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_contracts_dates ON contracts(start_date, end_date) WHERE is_deleted = FALSE;

-- ============================================
-- 3. 更新 users 表
-- ============================================

-- 新增 username 欄位
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS username VARCHAR(100);

-- 從 email 提取 username
UPDATE users
SET username = SPLIT_PART(email, '@', 1)
WHERE username IS NULL;

-- 設定 username 為必填
ALTER TABLE users
    ALTER COLUMN username SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- 新增 user_type 欄位
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS user_type VARCHAR(20) DEFAULT 'EMPLOYEE';

-- 遷移現有的角色 (僅升級時有效，全新安裝時舊欄位不存在則跳過)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'is_system_admin'
    ) THEN
        UPDATE users SET user_type = 'SYSTEM_ADMIN' WHERE is_system_admin = TRUE;
        UPDATE users SET user_type = 'ORG_ADMIN' WHERE is_org_admin = TRUE AND is_system_admin = FALSE;
    END IF;
END $$;

-- 新增主要組織單位欄位 (稍後會建立外鍵)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS primary_unit_secure_code VARCHAR(32);

-- 建立組織內唯一約束
-- 先刪除可能存在的舊約束
ALTER TABLE users DROP CONSTRAINT IF EXISTS unique_user_org;

-- 建立新約束
ALTER TABLE users
    ADD CONSTRAINT unique_user_org UNIQUE (username, org_secure_code);

-- ============================================
-- 4. 建立 organizational_units 表 (部門/群組)
-- ============================================

CREATE TABLE IF NOT EXISTS organizational_units (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code) ON UPDATE CASCADE,

    unit_type VARCHAR(20) NOT NULL DEFAULT 'DEPARTMENT',
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,

    parent_secure_code VARCHAR(32) REFERENCES organizational_units(secure_code) ON UPDATE CASCADE,
    full_path VARCHAR(1000),
    level INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    member_role_secure_code VARCHAR(32),

    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_org_units_org ON organizational_units(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_org_units_parent ON organizational_units(parent_secure_code);
CREATE INDEX IF NOT EXISTS idx_org_units_type ON organizational_units(unit_type) WHERE is_deleted = FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS idx_org_units_code_org ON organizational_units(code, org_secure_code) WHERE is_deleted = FALSE;

-- ============================================
-- 5. 建立 roles 表 (職務/角色)
-- ============================================

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code) ON UPDATE CASCADE,

    role_type VARCHAR(20) NOT NULL DEFAULT 'ROLE',
    scope_type VARCHAR(20) NOT NULL DEFAULT 'GLOBAL',
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,

    parent_secure_code VARCHAR(32) REFERENCES roles(secure_code) ON UPDATE CASCADE,
    full_path VARCHAR(1000),
    level INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,

    is_manager BOOLEAN NOT NULL DEFAULT FALSE,
    is_system_role BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    permissions TEXT,
    bound_unit_secure_code VARCHAR(32) REFERENCES organizational_units(secure_code) ON UPDATE CASCADE,

    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_roles_org ON roles(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_roles_parent ON roles(parent_secure_code);
CREATE INDEX IF NOT EXISTS idx_roles_type ON roles(role_type) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_roles_scope ON roles(scope_type) WHERE is_deleted = FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS idx_roles_code_org ON roles(code, org_secure_code) WHERE is_deleted = FALSE;

-- ============================================
-- 6. 建立 user_unit_assignments 表 (用戶-組織單位關聯)
-- ============================================

CREATE TABLE IF NOT EXISTS user_unit_assignments (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code) ON UPDATE CASCADE,

    user_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code) ON UPDATE CASCADE,
    unit_secure_code VARCHAR(32) NOT NULL REFERENCES organizational_units(secure_code) ON UPDATE CASCADE,

    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
    assigned_by VARCHAR(100),

    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_unit_user ON user_unit_assignments(user_secure_code);
CREATE INDEX IF NOT EXISTS idx_user_unit_unit ON user_unit_assignments(unit_secure_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_unit_unique ON user_unit_assignments(user_secure_code, unit_secure_code) WHERE is_deleted = FALSE;

-- ============================================
-- 7. 建立 user_role_assignments 表 (用戶-角色關聯)
-- ============================================

CREATE TABLE IF NOT EXISTS user_role_assignments (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code) ON UPDATE CASCADE,

    user_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code) ON UPDATE CASCADE,
    role_secure_code VARCHAR(32) NOT NULL REFERENCES roles(secure_code) ON UPDATE CASCADE,
    unit_secure_code VARCHAR(32) REFERENCES organizational_units(secure_code) ON UPDATE CASCADE,

    valid_from DATE,
    valid_until DATE,

    assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
    assigned_by VARCHAR(100),

    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_role_user ON user_role_assignments(user_secure_code);
CREATE INDEX IF NOT EXISTS idx_user_role_role ON user_role_assignments(role_secure_code);
CREATE INDEX IF NOT EXISTS idx_user_role_unit ON user_role_assignments(unit_secure_code);

-- ============================================
-- 8. 新增 users 表的外鍵 (需在 organizational_units 建立後)
-- ============================================

-- 暫時不加外鍵，因為 primary_unit_secure_code 可能為 NULL
-- 如需要可在應用層驗證

-- ============================================
-- 9. SEED DATA
-- ============================================
-- 注意: Seed 資料現在由 Python 腳本建立，確保 secure_code 使用 token_urlsafe(16) 生成
-- 執行方式: python scripts/seed_data.py
--
-- 不要在此處硬編碼 secure_code！這會造成安全風險（可被猜測）

-- ============================================
-- 資料表註解
-- ============================================
COMMENT ON TABLE contracts IS '企業合約表 - 記錄企業客戶的服務合約與計費資訊';
COMMENT ON TABLE organizational_units IS '組織單位表 - 部門、群組等組織架構的樹狀結構';
COMMENT ON TABLE roles IS '角色/職務表 - 定義權限角色與職務頭銜';
COMMENT ON TABLE user_unit_assignments IS '用戶-組織單位關聯表 - 企業成員的部門歸屬';
COMMENT ON TABLE user_role_assignments IS '用戶-角色關聯表 - 企業成員的角色指派';

-- ============================================
-- organizations 新增欄位註解
-- ============================================
COMMENT ON COLUMN organizations.domain_name IS '企業網域名稱，用於 SSO 和 Email 匹配';
COMMENT ON COLUMN organizations.customer_type IS '客戶類型: TRIAL=試用, FORMAL=正式, PARTNER=合作夥伴';
COMMENT ON COLUMN organizations.user_limit IS '用戶數量上限，依合約決定';
COMMENT ON COLUMN organizations.contact_person IS '主要聯絡人姓名';
COMMENT ON COLUMN organizations.contact_email IS '主要聯絡人 Email';
COMMENT ON COLUMN organizations.contact_phone IS '主要聯絡人電話';
COMMENT ON COLUMN organizations.address IS '企業地址';

-- ============================================
-- contracts 欄位註解
-- ============================================
COMMENT ON COLUMN contracts.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN contracts.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN contracts.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN contracts.contract_number IS '合約編號，全系統唯一';
COMMENT ON COLUMN contracts.name IS '合約名稱';
COMMENT ON COLUMN contracts.description IS '合約描述';
COMMENT ON COLUMN contracts.start_date IS '合約開始日期';
COMMENT ON COLUMN contracts.end_date IS '合約結束日期';
COMMENT ON COLUMN contracts.amount IS '合約金額';
COMMENT ON COLUMN contracts.status IS '合約狀態: DRAFT=草稿, ACTIVE=生效中, EXPIRED=已過期, TERMINATED=已終止';
COMMENT ON COLUMN contracts.modules_config IS '授權模組設定 (JSON 格式)';
COMMENT ON COLUMN contracts.notes IS '備註';
COMMENT ON COLUMN contracts.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN contracts.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN contracts.created_at IS '建立時間';
COMMENT ON COLUMN contracts.updated_at IS '最後更新時間';

-- ============================================
-- users 新增欄位註解
-- ============================================
COMMENT ON COLUMN users.username IS '用戶名稱，同企業內唯一';
COMMENT ON COLUMN users.user_type IS '用戶類型: SYSTEM_ADMIN=系統管理員, ORG_ADMIN=企業管理員, EMPLOYEE=企業成員, EXTERNAL=外部廠商';
COMMENT ON COLUMN users.primary_unit_secure_code IS '主要部門識別碼，企業成員的主要歸屬單位';

-- ============================================
-- organizational_units 欄位註解
-- ============================================
COMMENT ON COLUMN organizational_units.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN organizational_units.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN organizational_units.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN organizational_units.unit_type IS '單位類型: DEPARTMENT=部門, GROUP=群組, TEAM=團隊, DIVISION=處室';
COMMENT ON COLUMN organizational_units.code IS '單位代碼，同企業內唯一';
COMMENT ON COLUMN organizational_units.name IS '單位名稱';
COMMENT ON COLUMN organizational_units.description IS '單位描述';
COMMENT ON COLUMN organizational_units.parent_secure_code IS '上層單位識別碼，用於建立組織樹';
COMMENT ON COLUMN organizational_units.full_path IS '完整路徑，如「總公司/資訊處/開發部」';
COMMENT ON COLUMN organizational_units.level IS '組織層級，1 為最高層';
COMMENT ON COLUMN organizational_units.sort_order IS '同層級內的排序順序';
COMMENT ON COLUMN organizational_units.is_active IS '是否啟用';
COMMENT ON COLUMN organizational_units.member_role_secure_code IS '預設成員角色識別碼';
COMMENT ON COLUMN organizational_units.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN organizational_units.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN organizational_units.created_at IS '建立時間';
COMMENT ON COLUMN organizational_units.updated_at IS '最後更新時間';

-- ============================================
-- roles 欄位註解
-- ============================================
COMMENT ON COLUMN roles.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN roles.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN roles.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN roles.role_type IS '角色類型: ROLE=權限角色, POSITION=職務頭銜';
COMMENT ON COLUMN roles.scope_type IS '權限範圍: GLOBAL=全企業, UNIT=特定單位, SELF=僅限自己';
COMMENT ON COLUMN roles.code IS '角色代碼，同企業內唯一';
COMMENT ON COLUMN roles.name IS '角色名稱';
COMMENT ON COLUMN roles.description IS '角色描述';
COMMENT ON COLUMN roles.parent_secure_code IS '上層角色識別碼，用於角色繼承';
COMMENT ON COLUMN roles.full_path IS '完整路徑';
COMMENT ON COLUMN roles.level IS '角色層級';
COMMENT ON COLUMN roles.sort_order IS '排序順序';
COMMENT ON COLUMN roles.is_manager IS '是否為管理者角色';
COMMENT ON COLUMN roles.is_system_role IS '是否為系統內建角色，TRUE 時不可刪除';
COMMENT ON COLUMN roles.is_active IS '是否啟用';
COMMENT ON COLUMN roles.permissions IS '權限設定 (JSON 格式)';
COMMENT ON COLUMN roles.bound_unit_secure_code IS '綁定的組織單位，用於 UNIT 範圍';
COMMENT ON COLUMN roles.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN roles.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN roles.created_at IS '建立時間';
COMMENT ON COLUMN roles.updated_at IS '最後更新時間';

-- ============================================
-- user_unit_assignments 欄位註解
-- ============================================
COMMENT ON COLUMN user_unit_assignments.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN user_unit_assignments.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN user_unit_assignments.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN user_unit_assignments.user_secure_code IS '用戶識別碼';
COMMENT ON COLUMN user_unit_assignments.unit_secure_code IS '組織單位識別碼';
COMMENT ON COLUMN user_unit_assignments.is_primary IS '是否為主要歸屬單位';
COMMENT ON COLUMN user_unit_assignments.assigned_at IS '指派時間';
COMMENT ON COLUMN user_unit_assignments.assigned_by IS '指派人';
COMMENT ON COLUMN user_unit_assignments.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN user_unit_assignments.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN user_unit_assignments.created_at IS '建立時間';
COMMENT ON COLUMN user_unit_assignments.updated_at IS '最後更新時間';

-- ============================================
-- user_role_assignments 欄位註解
-- ============================================
COMMENT ON COLUMN user_role_assignments.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN user_role_assignments.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN user_role_assignments.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN user_role_assignments.user_secure_code IS '用戶識別碼';
COMMENT ON COLUMN user_role_assignments.role_secure_code IS '角色識別碼';
COMMENT ON COLUMN user_role_assignments.unit_secure_code IS '生效範圍的組織單位 (若角色為 UNIT 範圍)';
COMMENT ON COLUMN user_role_assignments.valid_from IS '角色生效開始日期';
COMMENT ON COLUMN user_role_assignments.valid_until IS '角色生效結束日期';
COMMENT ON COLUMN user_role_assignments.assigned_at IS '指派時間';
COMMENT ON COLUMN user_role_assignments.assigned_by IS '指派人';
COMMENT ON COLUMN user_role_assignments.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN user_role_assignments.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN user_role_assignments.created_at IS '建立時間';
COMMENT ON COLUMN user_role_assignments.updated_at IS '最後更新時間';
