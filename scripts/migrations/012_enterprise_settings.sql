-- ============================================================
-- 012_enterprise_settings.sql
-- 企業級設定表（SMTP、Telegram）
-- ============================================================

-- SMTP 設定表
CREATE TABLE IF NOT EXISTS smtp_configs (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 設定資訊
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- SMTP 伺服器設定
    smtp_host VARCHAR(255) NOT NULL,
    smtp_port INTEGER NOT NULL DEFAULT 587,
    use_tls BOOLEAN NOT NULL DEFAULT TRUE,
    use_ssl BOOLEAN NOT NULL DEFAULT FALSE,

    -- 認證資訊
    username VARCHAR(255) NOT NULL,
    password_encrypted VARCHAR(512),

    -- 寄件人資訊
    from_email VARCHAR(255) NOT NULL,
    from_name VARCHAR(100),

    -- 提供者類型
    provider_type VARCHAR(20) NOT NULL DEFAULT 'generic',

    -- 優先順序與狀態
    priority INTEGER NOT NULL DEFAULT 100,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- 測試狀態
    last_test_at TIMESTAMP,
    last_test_success BOOLEAN,
    last_test_message TEXT,

    -- 標準欄位
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_smtp_configs_org ON smtp_configs(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_smtp_configs_deleted ON smtp_configs(is_deleted);

-- 欄位註解
COMMENT ON TABLE smtp_configs IS 'SMTP 郵件伺服器設定';
COMMENT ON COLUMN smtp_configs.secure_code IS '外部識別碼';
COMMENT ON COLUMN smtp_configs.org_secure_code IS '所屬企業';
COMMENT ON COLUMN smtp_configs.name IS '設定名稱';
COMMENT ON COLUMN smtp_configs.description IS '描述說明';
COMMENT ON COLUMN smtp_configs.smtp_host IS 'SMTP 伺服器位址';
COMMENT ON COLUMN smtp_configs.smtp_port IS 'SMTP 連接埠';
COMMENT ON COLUMN smtp_configs.use_tls IS '使用 STARTTLS';
COMMENT ON COLUMN smtp_configs.use_ssl IS '使用 SSL/TLS';
COMMENT ON COLUMN smtp_configs.username IS 'SMTP 帳號';
COMMENT ON COLUMN smtp_configs.password_encrypted IS '加密後的密碼 (Base64)';
COMMENT ON COLUMN smtp_configs.from_email IS '寄件人信箱';
COMMENT ON COLUMN smtp_configs.from_name IS '寄件人名稱';
COMMENT ON COLUMN smtp_configs.provider_type IS '提供者類型: generic, gmail, outlook';
COMMENT ON COLUMN smtp_configs.priority IS '優先順序（數字越小越優先）';
COMMENT ON COLUMN smtp_configs.is_default IS '是否為預設設定';
COMMENT ON COLUMN smtp_configs.is_active IS '是否啟用';
COMMENT ON COLUMN smtp_configs.last_test_at IS '最後測試時間';
COMMENT ON COLUMN smtp_configs.last_test_success IS '最後測試結果';
COMMENT ON COLUMN smtp_configs.last_test_message IS '最後測試訊息';


-- Telegram 設定表
CREATE TABLE IF NOT EXISTS telegram_configs (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 設定資訊
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- Bot 設定
    bot_token VARCHAR(255) NOT NULL,
    channels TEXT,  -- JSON 格式: {"頻道名": "chat_id", ...}
    default_channel VARCHAR(100),

    -- 狀態
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- 標準欄位
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_telegram_configs_org ON telegram_configs(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_telegram_configs_deleted ON telegram_configs(is_deleted);

-- 欄位註解
COMMENT ON TABLE telegram_configs IS 'Telegram Bot 設定';
COMMENT ON COLUMN telegram_configs.secure_code IS '外部識別碼';
COMMENT ON COLUMN telegram_configs.org_secure_code IS '所屬企業';
COMMENT ON COLUMN telegram_configs.name IS '設定名稱';
COMMENT ON COLUMN telegram_configs.description IS '描述說明';
COMMENT ON COLUMN telegram_configs.bot_token IS 'Telegram Bot Token';
COMMENT ON COLUMN telegram_configs.channels IS '頻道設定 JSON';
COMMENT ON COLUMN telegram_configs.default_channel IS '預設頻道名稱';
COMMENT ON COLUMN telegram_configs.is_active IS '是否啟用';


-- ============================================================
-- 執行結果輸出
-- ============================================================
SELECT 'Migration 012_enterprise_settings.sql completed successfully' AS status;
