-- 044: 表單中心欄位顯示設定
-- 企業級設定：管理員可依語系配置各欄位寬度與是否隱藏

CREATE TABLE IF NOT EXISTS fw_column_display_config (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    locale VARCHAR(10) NOT NULL DEFAULT '*',
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    CONSTRAINT uq_fw_col_config_org_locale UNIQUE (org_secure_code, locale)
);

CREATE INDEX IF NOT EXISTS ix_fw_col_config_org ON fw_column_display_config (org_secure_code);
CREATE INDEX IF NOT EXISTS ix_fw_col_config_secure_code ON fw_column_display_config (secure_code);
