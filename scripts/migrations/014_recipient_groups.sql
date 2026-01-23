-- ============================================================
-- 014_recipient_groups.sql
-- 收件人群組設定表
-- ============================================================

-- 收件人群組表
CREATE TABLE IF NOT EXISTS recipient_groups (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 群組資訊
    name VARCHAR(100) NOT NULL,
    description TEXT,
    priority INTEGER NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- 收件人設定（JSON 格式）
    included_units TEXT,      -- [{"id": "xxx", "include_children": true}, ...]
    included_users TEXT,      -- ["user_id_1", "user_id_2", ...]
    excluded_units TEXT,      -- ["unit_id_1", "unit_id_2", ...]
    excluded_users TEXT,      -- ["user_id_1", "user_id_2", ...]

    -- 標準欄位
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_recipient_groups_org ON recipient_groups(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_recipient_groups_deleted ON recipient_groups(is_deleted);
CREATE INDEX IF NOT EXISTS idx_recipient_groups_active ON recipient_groups(is_active);

-- 欄位註解
COMMENT ON TABLE recipient_groups IS '收件人群組設定';
COMMENT ON COLUMN recipient_groups.secure_code IS '外部識別碼';
COMMENT ON COLUMN recipient_groups.org_secure_code IS '所屬企業';
COMMENT ON COLUMN recipient_groups.name IS '群組名稱';
COMMENT ON COLUMN recipient_groups.description IS '描述說明';
COMMENT ON COLUMN recipient_groups.priority IS '優先順序（數字越小越優先）';
COMMENT ON COLUMN recipient_groups.is_active IS '是否啟用';
COMMENT ON COLUMN recipient_groups.included_units IS '包含的部門（JSON）';
COMMENT ON COLUMN recipient_groups.included_users IS '包含的用戶（JSON）';
COMMENT ON COLUMN recipient_groups.excluded_units IS '排除的部門（JSON）';
COMMENT ON COLUMN recipient_groups.excluded_users IS '排除的用戶（JSON）';

-- ============================================================
-- 執行結果輸出
-- ============================================================
SELECT 'Migration 014_recipient_groups.sql completed successfully' AS status;
