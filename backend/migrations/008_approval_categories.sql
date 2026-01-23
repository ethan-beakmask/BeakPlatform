-- Migration 008: 核決權限類別系統
-- 建立 approval_categories 和 job_level_approval_limits 資料表
-- 取代原本 job_levels.approval_limit 單一欄位

BEGIN;

-- 1. 建立核決權限類別表
CREATE TABLE IF NOT EXISTS approval_categories (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    name_en VARCHAR(100),
    description TEXT,
    currency VARCHAR(3) NOT NULL DEFAULT 'TWD',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_system_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_approval_categories_org ON approval_categories(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_approval_categories_code ON approval_categories(code);
CREATE INDEX IF NOT EXISTS idx_approval_categories_deleted ON approval_categories(is_deleted);

COMMENT ON TABLE approval_categories IS '核決權限類別';
COMMENT ON COLUMN approval_categories.code IS '類別代碼';
COMMENT ON COLUMN approval_categories.name IS '類別名稱';
COMMENT ON COLUMN approval_categories.name_en IS '類別英文名稱';
COMMENT ON COLUMN approval_categories.description IS '類別描述';
COMMENT ON COLUMN approval_categories.currency IS '幣別';
COMMENT ON COLUMN approval_categories.sort_order IS '排序順序';
COMMENT ON COLUMN approval_categories.is_system_default IS '是否為系統預設';
COMMENT ON COLUMN approval_categories.is_active IS '是否啟用';

-- 2. 建立職等核決上限關聯表
CREATE TABLE IF NOT EXISTS job_level_approval_limits (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    job_level_secure_code VARCHAR(32) NOT NULL REFERENCES job_levels(secure_code),
    category_secure_code VARCHAR(32) NOT NULL REFERENCES approval_categories(secure_code),
    approval_limit NUMERIC(15, 2),  -- NULL = 無上限

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 確保每個職等+類別組合唯一
    UNIQUE(org_secure_code, job_level_secure_code, category_secure_code)
);

CREATE INDEX IF NOT EXISTS idx_job_level_approval_limits_org ON job_level_approval_limits(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_job_level_approval_limits_level ON job_level_approval_limits(job_level_secure_code);
CREATE INDEX IF NOT EXISTS idx_job_level_approval_limits_category ON job_level_approval_limits(category_secure_code);
CREATE INDEX IF NOT EXISTS idx_job_level_approval_limits_deleted ON job_level_approval_limits(is_deleted);

COMMENT ON TABLE job_level_approval_limits IS '職等核決上限';
COMMENT ON COLUMN job_level_approval_limits.job_level_secure_code IS '職等 secure_code';
COMMENT ON COLUMN job_level_approval_limits.category_secure_code IS '類別 secure_code';
COMMENT ON COLUMN job_level_approval_limits.approval_limit IS '核決金額上限 (NULL=無上限)';

-- 3. 移除 job_levels 中舊的 approval_limit 欄位會破壞向下相容
-- 保留欄位但標記為棄用，未來版本再移除
-- ALTER TABLE job_levels DROP COLUMN IF EXISTS approval_limit;
-- ALTER TABLE job_levels DROP COLUMN IF EXISTS approval_currency;

COMMIT;
