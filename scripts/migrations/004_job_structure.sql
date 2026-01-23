-- Migration: 004_job_structure
-- Description: 新增職等職系結構，支援大型企業的人資架構
-- Date: 2024-12-20
-- Reference: OG-01-01 公司職稱職等對照表

-- ============================================================
-- 1. job_levels 職等資料表
-- ============================================================
CREATE TABLE IF NOT EXISTS job_levels (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 職等資訊
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    name_en VARCHAR(100),
    level_order INTEGER NOT NULL,

    -- 簽核權限
    approval_limit NUMERIC(15, 2),
    approval_currency VARCHAR(3) DEFAULT 'TWD' NOT NULL,

    -- 屬性
    is_manager_level BOOLEAN DEFAULT FALSE NOT NULL,
    management_scope VARCHAR(100),
    description TEXT,
    sort_order INTEGER DEFAULT 0 NOT NULL,
    is_system_default BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,

    -- 軟刪除
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,

    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_levels_org ON job_levels(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_job_levels_code ON job_levels(code);
CREATE INDEX IF NOT EXISTS idx_job_levels_order ON job_levels(level_order);
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_levels_org_code ON job_levels(org_secure_code, code) WHERE is_deleted = FALSE;

-- ============================================================
-- 2. job_families 職系資料表
-- ============================================================
CREATE TABLE IF NOT EXISTS job_families (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 職系資訊
    family_type VARCHAR(20) NOT NULL CHECK (family_type IN ('MANAGER', 'PROFESSIONAL')),
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    name_en VARCHAR(100),
    parent_secure_code VARCHAR(32) REFERENCES job_families(secure_code),
    description TEXT,

    -- 屬性
    sort_order INTEGER DEFAULT 0 NOT NULL,
    is_system_default BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,

    -- 軟刪除
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,

    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_families_org ON job_families(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_job_families_type ON job_families(family_type);
CREATE INDEX IF NOT EXISTS idx_job_families_parent ON job_families(parent_secure_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_families_org_code ON job_families(org_secure_code, code) WHERE is_deleted = FALSE;

-- ============================================================
-- 3. job_titles 職稱資料表
-- ============================================================
CREATE TABLE IF NOT EXISTS job_titles (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 職稱資訊
    code VARCHAR(30) NOT NULL,
    name VARCHAR(100) NOT NULL,
    name_en VARCHAR(100),
    short_name VARCHAR(50),
    description TEXT,

    -- 對應職等職系
    job_level_secure_code VARCHAR(32) NOT NULL REFERENCES job_levels(secure_code),
    job_family_secure_code VARCHAR(32) NOT NULL REFERENCES job_families(secure_code),

    -- 屬性
    is_supervisor BOOLEAN DEFAULT FALSE NOT NULL,
    sort_order INTEGER DEFAULT 0 NOT NULL,
    is_system_default BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,

    -- 軟刪除
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,

    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_titles_org ON job_titles(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_job_titles_level ON job_titles(job_level_secure_code);
CREATE INDEX IF NOT EXISTS idx_job_titles_family ON job_titles(job_family_secure_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_titles_org_code ON job_titles(org_secure_code, code) WHERE is_deleted = FALSE;

-- ============================================================
-- 4. employee_positions 員工職位資料表
-- ============================================================
CREATE TABLE IF NOT EXISTS employee_positions (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 關聯
    user_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code),
    job_title_secure_code VARCHAR(32) NOT NULL REFERENCES job_titles(secure_code),
    unit_secure_code VARCHAR(32) NOT NULL REFERENCES organizational_units(secure_code),

    -- 職位類型
    position_type VARCHAR(20) DEFAULT 'PRIMARY' NOT NULL
        CHECK (position_type IN ('PRIMARY', 'CONCURRENT', 'ACTING', 'TEMPORARY')),

    -- 主管關係 (最重要！)
    is_unit_head BOOLEAN DEFAULT FALSE NOT NULL,
    direct_manager_secure_code VARCHAR(32) REFERENCES users(secure_code),
    dotted_line_manager_secure_code VARCHAR(32) REFERENCES users(secure_code),

    -- 有效期限
    effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_until DATE,

    -- 其他
    remarks TEXT,
    assigned_by VARCHAR(100),
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,

    -- 軟刪除
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,

    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_emp_pos_org ON employee_positions(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_emp_pos_user ON employee_positions(user_secure_code);
CREATE INDEX IF NOT EXISTS idx_emp_pos_title ON employee_positions(job_title_secure_code);
CREATE INDEX IF NOT EXISTS idx_emp_pos_unit ON employee_positions(unit_secure_code);
CREATE INDEX IF NOT EXISTS idx_emp_pos_type ON employee_positions(position_type);
CREATE INDEX IF NOT EXISTS idx_emp_pos_manager ON employee_positions(direct_manager_secure_code);

-- ============================================================
-- 5. delegations 代理授權資料表
-- ============================================================
CREATE TABLE IF NOT EXISTS delegations (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 授權關係
    delegator_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code),
    delegate_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code),

    -- 代理類型
    delegation_type VARCHAR(20) DEFAULT 'FULL' NOT NULL
        CHECK (delegation_type IN ('FULL', 'APPROVAL', 'SPECIFIC')),
    status VARCHAR(20) DEFAULT 'PENDING' NOT NULL
        CHECK (status IN ('PENDING', 'ACTIVE', 'EXPIRED', 'REVOKED')),

    -- 有效期限
    effective_from DATE NOT NULL,
    effective_until DATE NOT NULL,

    -- 權限限制
    approval_limit NUMERIC(15, 2),
    approval_currency VARCHAR(3) DEFAULT 'TWD' NOT NULL,
    allowed_process_types TEXT,

    -- 原因
    reason TEXT,
    created_by VARCHAR(100),

    -- 撤銷資訊
    revoked_at TIMESTAMP,
    revoked_by VARCHAR(100),
    revoke_reason TEXT,

    -- 軟刪除
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    deleted_at TIMESTAMP,

    -- 審計
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_delegations_org ON delegations(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_delegations_delegator ON delegations(delegator_secure_code);
CREATE INDEX IF NOT EXISTS idx_delegations_delegate ON delegations(delegate_secure_code);
CREATE INDEX IF NOT EXISTS idx_delegations_status ON delegations(status);
CREATE INDEX IF NOT EXISTS idx_delegations_effective ON delegations(effective_from, effective_until);

-- ============================================================
-- 資料表註解
-- ============================================================
COMMENT ON TABLE job_levels IS '職等資料表 - 定義組織內的層級結構，使用等距跳號 L000-L900';
COMMENT ON TABLE job_families IS '職系資料表 - 定義職涯發展軌道 (管理職 MANAGER / 專業職 PROFESSIONAL)';
COMMENT ON TABLE job_titles IS '職稱資料表 - 職等與職系的具體組合，如「經理」= L500 + MGR';
COMMENT ON TABLE employee_positions IS '員工職位資料表 - 紀錄員工的職位指派、部門歸屬與主管關係';
COMMENT ON TABLE delegations IS '代理授權資料表 - 職務代理機制，避免主管不在時流程卡住';

-- ============================================================
-- job_levels 欄位註解
-- ============================================================
COMMENT ON COLUMN job_levels.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN job_levels.secure_code IS '外部識別碼 (32 字元)，對外暴露使用，取代自增 ID';
COMMENT ON COLUMN job_levels.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN job_levels.code IS '職等代碼，如 L100, L200, L500，等距跳號設計';
COMMENT ON COLUMN job_levels.name IS '職等名稱 (中文)，如「職員級」「經理級」';
COMMENT ON COLUMN job_levels.name_en IS '職等名稱 (英文)，如 Staff Level, Manager Level';
COMMENT ON COLUMN job_levels.level_order IS '職等序號，數字越大職等越高，用於比較與排序';
COMMENT ON COLUMN job_levels.approval_limit IS '簽核權限金額上限，NULL 表示無上限 (總經理級)';
COMMENT ON COLUMN job_levels.approval_currency IS '簽核權限幣別，預設 TWD';
COMMENT ON COLUMN job_levels.is_manager_level IS '是否為管理職等，L300 以上通常為 TRUE';
COMMENT ON COLUMN job_levels.management_scope IS '管理幅度說明，如「單一部門」「全公司」';
COMMENT ON COLUMN job_levels.description IS '職等描述，詳細說明此職等的定位與責任';
COMMENT ON COLUMN job_levels.sort_order IS '顯示排序順序，用於 UI 列表排序';
COMMENT ON COLUMN job_levels.is_system_default IS '是否為系統預設，TRUE 時不可刪除';
COMMENT ON COLUMN job_levels.is_active IS '是否啟用，FALSE 時不出現在選單中';
COMMENT ON COLUMN job_levels.is_deleted IS '軟刪除標記，TRUE 表示已刪除但保留資料';
COMMENT ON COLUMN job_levels.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN job_levels.created_at IS '建立時間';
COMMENT ON COLUMN job_levels.updated_at IS '最後更新時間';

-- ============================================================
-- job_families 欄位註解
-- ============================================================
COMMENT ON COLUMN job_families.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN job_families.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN job_families.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN job_families.family_type IS '職系類型：MANAGER 管理職 (帶人) / PROFESSIONAL 專業職 (不帶人)';
COMMENT ON COLUMN job_families.code IS '職系代碼，如 MGR, PROF, SALES, TECH';
COMMENT ON COLUMN job_families.name IS '職系名稱 (中文)，如「管理職」「業務職」';
COMMENT ON COLUMN job_families.name_en IS '職系名稱 (英文)，如 Management, Sales';
COMMENT ON COLUMN job_families.parent_secure_code IS '上層職系識別碼，用於子職系 (如 SALES 屬於 PROF)';
COMMENT ON COLUMN job_families.description IS '職系描述，說明此職系的職涯發展路線';
COMMENT ON COLUMN job_families.sort_order IS '顯示排序順序';
COMMENT ON COLUMN job_families.is_system_default IS '是否為系統預設，TRUE 時不可刪除';
COMMENT ON COLUMN job_families.is_active IS '是否啟用';
COMMENT ON COLUMN job_families.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN job_families.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN job_families.created_at IS '建立時間';
COMMENT ON COLUMN job_families.updated_at IS '最後更新時間';

-- ============================================================
-- job_titles 欄位註解
-- ============================================================
COMMENT ON COLUMN job_titles.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN job_titles.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN job_titles.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN job_titles.code IS '職稱代碼，如 MGR, PM, SR_ENG';
COMMENT ON COLUMN job_titles.name IS '職稱名稱 (中文)，如「經理」「專案經理」';
COMMENT ON COLUMN job_titles.name_en IS '職稱名稱 (英文)，如 Manager, Project Manager';
COMMENT ON COLUMN job_titles.short_name IS '職稱簡稱，用於空間有限的 UI 顯示';
COMMENT ON COLUMN job_titles.description IS '職責說明，描述此職稱的工作內容';
COMMENT ON COLUMN job_titles.job_level_secure_code IS '對應職等識別碼，決定簽核權限金額';
COMMENT ON COLUMN job_titles.job_family_secure_code IS '對應職系識別碼，決定職涯發展軌道';
COMMENT ON COLUMN job_titles.is_supervisor IS '是否為主管職稱 (帶人)，影響組織圖顯示';
COMMENT ON COLUMN job_titles.sort_order IS '顯示排序順序';
COMMENT ON COLUMN job_titles.is_system_default IS '是否為系統預設，TRUE 時不可刪除';
COMMENT ON COLUMN job_titles.is_active IS '是否啟用';
COMMENT ON COLUMN job_titles.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN job_titles.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN job_titles.created_at IS '建立時間';
COMMENT ON COLUMN job_titles.updated_at IS '最後更新時間';

-- ============================================================
-- employee_positions 欄位註解
-- ============================================================
COMMENT ON COLUMN employee_positions.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN employee_positions.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN employee_positions.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN employee_positions.user_secure_code IS '員工識別碼，指向 users 表';
COMMENT ON COLUMN employee_positions.job_title_secure_code IS '職稱識別碼，決定員工的正式頭銜';
COMMENT ON COLUMN employee_positions.unit_secure_code IS '部門識別碼，員工所屬的組織單位';
COMMENT ON COLUMN employee_positions.position_type IS '職位類型：PRIMARY 主要職位 / CONCURRENT 兼任 / ACTING 代理 / TEMPORARY 臨時';
COMMENT ON COLUMN employee_positions.is_unit_head IS '是否為部門主管，TRUE 時為該部門負責人';
COMMENT ON COLUMN employee_positions.direct_manager_secure_code IS '直屬主管識別碼 - 表單簽核流程最重要的欄位，決定第一關簽核人';
COMMENT ON COLUMN employee_positions.dotted_line_manager_secure_code IS '虛線主管識別碼 - Matrix 組織的專案主管，非正式彙報線';
COMMENT ON COLUMN employee_positions.effective_from IS '生效日期，職位指派的開始日期';
COMMENT ON COLUMN employee_positions.effective_until IS '失效日期，NULL 表示無期限，離職或調動時設定';
COMMENT ON COLUMN employee_positions.remarks IS '備註，記錄特殊情況說明';
COMMENT ON COLUMN employee_positions.assigned_by IS '指派人，記錄是誰做了此職位指派';
COMMENT ON COLUMN employee_positions.assigned_at IS '指派時間';
COMMENT ON COLUMN employee_positions.is_active IS '是否啟用，用於暫時停用職位';
COMMENT ON COLUMN employee_positions.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN employee_positions.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN employee_positions.created_at IS '建立時間';
COMMENT ON COLUMN employee_positions.updated_at IS '最後更新時間';

-- ============================================================
-- delegations 欄位註解
-- ============================================================
COMMENT ON COLUMN delegations.id IS '內部自增主鍵，僅供資料庫內部使用';
COMMENT ON COLUMN delegations.secure_code IS '外部識別碼 (32 字元)，對外暴露使用';
COMMENT ON COLUMN delegations.org_secure_code IS '所屬企業識別碼，多租戶隔離欄位';
COMMENT ON COLUMN delegations.delegator_secure_code IS '授權人識別碼 - 原本應該簽核的人';
COMMENT ON COLUMN delegations.delegate_secure_code IS '被授權人識別碼 - 代理簽核的人';
COMMENT ON COLUMN delegations.delegation_type IS '代理類型：FULL 全權代理 / APPROVAL 限額代理 / SPECIFIC 特定流程代理';
COMMENT ON COLUMN delegations.status IS '代理狀態：PENDING 待生效 / ACTIVE 生效中 / EXPIRED 已過期 / REVOKED 已撤銷';
COMMENT ON COLUMN delegations.effective_from IS '生效開始日期';
COMMENT ON COLUMN delegations.effective_until IS '生效結束日期';
COMMENT ON COLUMN delegations.approval_limit IS '簽核金額上限 - NULL 表示使用授權人原有權限，有值則為限額代理';
COMMENT ON COLUMN delegations.approval_currency IS '簽核權限幣別，預設 TWD';
COMMENT ON COLUMN delegations.allowed_process_types IS '允許的流程類型 (JSON 陣列)，用於特定流程代理';
COMMENT ON COLUMN delegations.reason IS '代理原因，如「出差」「請假」「受訓」';
COMMENT ON COLUMN delegations.created_by IS '建立者，記錄是誰設定了此代理';
COMMENT ON COLUMN delegations.revoked_at IS '撤銷時間';
COMMENT ON COLUMN delegations.revoked_by IS '撤銷者';
COMMENT ON COLUMN delegations.revoke_reason IS '撤銷原因';
COMMENT ON COLUMN delegations.is_deleted IS '軟刪除標記';
COMMENT ON COLUMN delegations.deleted_at IS '軟刪除時間戳';
COMMENT ON COLUMN delegations.created_at IS '建立時間';
COMMENT ON COLUMN delegations.updated_at IS '最後更新時間';
