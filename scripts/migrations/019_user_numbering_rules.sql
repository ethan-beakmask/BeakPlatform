-- ============================================================
-- 用戶編號規則資料庫遷移腳本
-- BeakMask v0.3.0
--
-- 功能：用戶編號自動產生規則
-- ============================================================

BEGIN;

-- ============================================================
-- 1. 編號規則主表
-- ============================================================
CREATE TABLE IF NOT EXISTS user_numbering_rules (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 基本資訊
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- 規則配置 (JSONB)
    -- 結構: {
    --   "total_length": 10,
    --   "components": [
    --     {"type": "prefix", "order": 1, "values": ["天","地","玄","黃"]},
    --     {"type": "year", "order": 2, "format": "yy"},
    --     {"type": "sequence", "order": 3, "digits": 4, "start": 1, "reset_period": "yearly"}
    --   ]
    -- }
    elements JSONB NOT NULL,

    -- 狀態
    usage_scope VARCHAR(20) NOT NULL DEFAULT 'INTERNAL_ONLY',
    default_for VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- 時間戳記
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_numbering_rules_org
    ON user_numbering_rules(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_numbering_rules_default
    ON user_numbering_rules(org_secure_code, default_for)
    WHERE is_deleted = FALSE AND is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_numbering_rules_secure_code
    ON user_numbering_rules(secure_code);

-- 欄位註解
COMMENT ON TABLE user_numbering_rules IS '用戶編號規則';
COMMENT ON COLUMN user_numbering_rules.secure_code IS '安全識別碼';
COMMENT ON COLUMN user_numbering_rules.org_secure_code IS '企業識別碼';
COMMENT ON COLUMN user_numbering_rules.name IS '規則名稱（如：企業成員編號、來賓編號）';
COMMENT ON COLUMN user_numbering_rules.description IS '規則描述';
COMMENT ON COLUMN user_numbering_rules.elements IS '編號元素配置 (JSONB)';
COMMENT ON COLUMN user_numbering_rules.default_for IS '預設用途: EMPLOYEE=企業成員預設, EXTERNAL=外部廠商預設, FORM=表單編號預設, NULL=非預設';
COMMENT ON COLUMN user_numbering_rules.is_active IS '是否啟用';

-- ============================================================
-- 2. 編號計數器表
-- ============================================================
CREATE TABLE IF NOT EXISTS user_numbering_counters (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 關聯規則
    rule_secure_code VARCHAR(32) NOT NULL REFERENCES user_numbering_rules(secure_code),

    -- 週期識別 (用於年/月重置)
    -- "2026" (每年重置), "2026-01" (每月重置), "all" (永不重置)
    period_key VARCHAR(20) NOT NULL,

    -- 計數器狀態
    prefix_index INTEGER NOT NULL DEFAULT 0,
    suffix_index INTEGER NOT NULL DEFAULT 0,
    current_seq INTEGER NOT NULL DEFAULT 0,

    -- 時間戳記
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 約束：每個規則在每個週期只能有一個計數器
    CONSTRAINT uq_numbering_counter UNIQUE (org_secure_code, rule_secure_code, period_key)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_numbering_counters_rule
    ON user_numbering_counters(rule_secure_code);
CREATE INDEX IF NOT EXISTS idx_numbering_counters_org
    ON user_numbering_counters(org_secure_code);

-- 欄位註解
COMMENT ON TABLE user_numbering_counters IS '用戶編號計數器';
COMMENT ON COLUMN user_numbering_counters.rule_secure_code IS '關聯的編號規則';
COMMENT ON COLUMN user_numbering_counters.period_key IS '週期識別（年/月/永久）';
COMMENT ON COLUMN user_numbering_counters.prefix_index IS '當前前綴索引';
COMMENT ON COLUMN user_numbering_counters.suffix_index IS '當前後綴索引';
COMMENT ON COLUMN user_numbering_counters.current_seq IS '當前序號';

-- ============================================================
-- 3. 已使用編號表（防止重複）
-- ============================================================
CREATE TABLE IF NOT EXISTS used_user_numbers (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 編號資訊
    number VARCHAR(50) NOT NULL,

    -- 關聯資訊（可選）
    user_secure_code VARCHAR(32) REFERENCES users(secure_code),
    rule_secure_code VARCHAR(32) REFERENCES user_numbering_rules(secure_code),

    -- 時間戳記
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,

    -- 約束：企業內編號唯一
    CONSTRAINT uq_used_number UNIQUE (org_secure_code, number)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_used_numbers_org
    ON used_user_numbers(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_used_numbers_user
    ON used_user_numbers(user_secure_code);
CREATE INDEX IF NOT EXISTS idx_used_numbers_number
    ON used_user_numbers(org_secure_code, number);

-- 欄位註解
COMMENT ON TABLE used_user_numbers IS '已使用的用戶編號（防止重複）';
COMMENT ON COLUMN used_user_numbers.number IS '編號值';
COMMENT ON COLUMN used_user_numbers.user_secure_code IS '使用此編號的用戶';
COMMENT ON COLUMN used_user_numbers.rule_secure_code IS '產生此編號的規則';

-- ============================================================
-- 4. 為每個企業建立預設規則
-- ============================================================
DO $$
DECLARE
    org RECORD;
    new_secure_code VARCHAR(32);
BEGIN
    FOR org IN SELECT secure_code FROM organizations WHERE is_deleted = FALSE
    LOOP
        -- 檢查是否已有預設規則
        IF NOT EXISTS (
            SELECT 1 FROM user_numbering_rules
            WHERE org_secure_code = org.secure_code
              AND default_for IS NOT NULL
              AND is_deleted = FALSE
        ) THEN
            -- 產生新的 secure_code
            new_secure_code := encode(gen_random_bytes(16), 'hex');

            -- 插入預設規則（明確指定所有 NOT NULL 欄位，不依賴 DEFAULT）
            INSERT INTO user_numbering_rules (
                secure_code,
                org_secure_code,
                name,
                description,
                elements,
                usage_scope,
                default_for,
                is_active,
                created_at,
                updated_at,
                is_deleted
            )
            VALUES (
                new_secure_code,
                org.secure_code,
                '預設編號',
                '系統預設的用戶編號規則（純序號）',
                '{
                    "total_length": 6,
                    "components": [
                        {
                            "type": "sequence",
                            "order": 1,
                            "digits": 6,
                            "start": 1,
                            "reset_period": "never"
                        }
                    ]
                }'::jsonb,
                'INTERNAL_ONLY',
                'EMPLOYEE',
                TRUE,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                FALSE
            );
        END IF;
    END LOOP;
END;
$$;

-- ============================================================
-- 5. 將現有 users.employee_id 記錄到 used_user_numbers
-- ============================================================
INSERT INTO used_user_numbers (secure_code, org_secure_code, number, user_secure_code,
    created_at, updated_at, is_deleted)
SELECT
    encode(gen_random_bytes(16), 'hex'),
    u.org_secure_code,
    u.employee_id,
    u.secure_code,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    FALSE
FROM users u
WHERE u.employee_id IS NOT NULL
  AND u.employee_id != ''
  AND u.is_deleted = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM used_user_numbers
      WHERE org_secure_code = u.org_secure_code
        AND number = u.employee_id
  );

COMMIT;
