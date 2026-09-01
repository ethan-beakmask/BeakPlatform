-- ============================================================
-- 013_smtp_app_password.sql
-- SMTP 設定新增 Gmail 應用程式密碼支援
-- ============================================================

-- 新增 use_app_password 欄位
ALTER TABLE smtp_configs
ADD COLUMN IF NOT EXISTS use_app_password BOOLEAN NOT NULL DEFAULT FALSE;

-- 欄位註解
COMMENT ON COLUMN smtp_configs.use_app_password IS '是否使用 Gmail 應用程式密碼';

-- 更新密碼欄位註解（現在使用 Fernet 加密）
COMMENT ON COLUMN smtp_configs.password_encrypted IS 'Fernet 加密後的密碼';

-- ============================================================
-- 執行結果輸出
-- ============================================================
SELECT 'Migration 013_smtp_app_password.sql completed successfully' AS status;
