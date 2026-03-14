-- 039_menu_role_requirements.sql
-- 選單角色需求表：定義每個選單項目需要哪些角色才能存取
-- 白名單制：無記錄 = 沿用現有 user_type 檢查，有記錄 = 必須持有其中至少一個角色
-- 各企業獨立設定

BEGIN;

CREATE TABLE IF NOT EXISTS menu_role_requirements (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,

    -- 選單項目
    menu_secure_code VARCHAR(32) NOT NULL REFERENCES menu_items(secure_code) ON DELETE CASCADE,

    -- 角色
    role_secure_code VARCHAR(32) NOT NULL REFERENCES roles(secure_code) ON DELETE CASCADE,

    -- 企業 (各企業獨立設定)
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 時間戳記
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 軟刪除
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 唯一約束：同一企業、同一選單、同一角色只能有一筆
    CONSTRAINT unique_menu_role_org UNIQUE (menu_secure_code, role_secure_code, org_secure_code)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_mrr_menu_sc ON menu_role_requirements(menu_secure_code);
CREATE INDEX IF NOT EXISTS idx_mrr_role_sc ON menu_role_requirements(role_secure_code);
CREATE INDEX IF NOT EXISTS idx_mrr_org_sc ON menu_role_requirements(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_mrr_is_deleted ON menu_role_requirements(is_deleted);

-- 複合索引：按企業+選單查詢（最常用的查詢模式）
CREATE INDEX IF NOT EXISTS idx_mrr_org_menu ON menu_role_requirements(org_secure_code, menu_secure_code)
    WHERE is_deleted = FALSE;

-- RLS
ALTER TABLE menu_role_requirements ENABLE ROW LEVEL SECURITY;
CREATE POLICY menu_role_requirements_org_policy ON menu_role_requirements
    USING (org_secure_code = current_setting('app.current_org', true)
           OR current_setting('app.is_system_admin', true) = 'true');

-- 授權
GRANT ALL PRIVILEGES ON TABLE menu_role_requirements TO beakplatform;
GRANT USAGE, SELECT ON SEQUENCE menu_role_requirements_id_seq TO beakplatform;

COMMIT;
