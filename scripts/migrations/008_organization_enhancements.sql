-- ============================================================
-- 008_organization_enhancements.sql
-- 企業登記功能強化
-- ============================================================

BEGIN;

-- ============================================================
-- 1. organizations 資料表 - 新增 display_name 欄位
-- ============================================================

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);

COMMENT ON COLUMN organizations.display_name IS '企業顯示名稱（多語言）';

-- ============================================================
-- 2. users 資料表 - 新增密碼變更與原始管理員欄位
-- ============================================================

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS is_original_admin BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN users.must_change_password IS '是否強制變更密碼';
COMMENT ON COLUMN users.password_changed_at IS '密碼變更時間';
COMMENT ON COLUMN users.is_original_admin IS '是否為企業原始管理員（無合約時唯一可登入）';

-- 更新現有企業管理員為原始管理員
-- 每個企業的第一個 ORG_ADMIN 設為原始管理員
UPDATE users u
SET is_original_admin = TRUE
WHERE u.user_type = 'ORG_ADMIN'
  AND u.is_deleted = FALSE
  AND u.id = (
      SELECT MIN(u2.id)
      FROM users u2
      WHERE u2.org_secure_code = u.org_secure_code
        AND u2.user_type = 'ORG_ADMIN'
        AND u2.is_deleted = FALSE
  );

-- ============================================================
-- 3. contracts 資料表 - 新增稽核欄位
-- ============================================================

ALTER TABLE contracts
    ADD COLUMN IF NOT EXISTS created_by_secure_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS modified_by_secure_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS modified_at TIMESTAMP;

-- 添加外鍵約束（如果不存在）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_contracts_created_by'
        AND table_name = 'contracts'
    ) THEN
        ALTER TABLE contracts
            ADD CONSTRAINT fk_contracts_created_by
            FOREIGN KEY (created_by_secure_code)
            REFERENCES users(secure_code);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_contracts_modified_by'
        AND table_name = 'contracts'
    ) THEN
        ALTER TABLE contracts
            ADD CONSTRAINT fk_contracts_modified_by
            FOREIGN KEY (modified_by_secure_code)
            REFERENCES users(secure_code);
    END IF;
END $$;

COMMENT ON COLUMN contracts.created_by_secure_code IS '建立者';
COMMENT ON COLUMN contracts.modified_by_secure_code IS '最後修改者';
COMMENT ON COLUMN contracts.modified_at IS '最後修改時間';

-- ============================================================
-- 4. 新增：公共信箱 Domain 黑名單表
-- ============================================================

CREATE TABLE IF NOT EXISTS blocked_email_domains (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL UNIQUE,
    reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE blocked_email_domains IS '禁止註冊的公共信箱 Domain';
COMMENT ON COLUMN blocked_email_domains.domain IS 'Email Domain（小寫）';
COMMENT ON COLUMN blocked_email_domains.reason IS '封鎖原因';

-- 內建拒絕清單
INSERT INTO blocked_email_domains (domain, reason) VALUES
    ('gmail.com', '公共信箱'),
    ('googlemail.com', '公共信箱'),
    ('yahoo.com', '公共信箱'),
    ('yahoo.com.tw', '公共信箱'),
    ('yahoo.co.jp', '公共信箱'),
    ('hotmail.com', '公共信箱'),
    ('outlook.com', '公共信箱'),
    ('live.com', '公共信箱'),
    ('msn.com', '公共信箱'),
    ('icloud.com', '公共信箱'),
    ('me.com', '公共信箱'),
    ('qq.com', '公共信箱'),
    ('163.com', '公共信箱'),
    ('126.com', '公共信箱'),
    ('sina.com', '公共信箱'),
    ('protonmail.com', '公共信箱'),
    ('proton.me', '公共信箱'),
    ('mail.com', '公共信箱'),
    ('ymail.com', '公共信箱'),
    ('aol.com', '公共信箱'),
    ('zoho.com', '公共信箱'),
    ('tutanota.com', '公共信箱'),
    ('gmx.com', '公共信箱'),
    ('gmx.net', '公共信箱'),
    ('web.de', '公共信箱'),
    ('mail.ru', '公共信箱'),
    ('yandex.com', '公共信箱'),
    ('yandex.ru', '公共信箱')
ON CONFLICT (domain) DO NOTHING;

-- ============================================================
-- 5. 索引優化
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_users_is_original_admin
    ON users(org_secure_code, is_original_admin)
    WHERE is_original_admin = TRUE AND is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_blocked_email_domains_domain
    ON blocked_email_domains(domain);

COMMIT;

-- ============================================================
-- 執行後驗證
-- ============================================================
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'organizations' AND column_name = 'display_name';
--
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'users' AND column_name IN ('must_change_password', 'password_changed_at', 'is_original_admin');
--
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'contracts' AND column_name IN ('created_by_secure_code', 'modified_by_secure_code', 'modified_at');
--
-- SELECT COUNT(*) FROM blocked_email_domains;
-- SELECT * FROM users WHERE is_original_admin = TRUE;
