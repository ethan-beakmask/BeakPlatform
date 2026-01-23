-- 012_password_policy.sql
-- 密碼複雜度政策

-- 密碼歷史表（儲存 bcrypt hash）
CREATE TABLE IF NOT EXISTS password_history (
    id SERIAL PRIMARY KEY,
    user_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code) ON DELETE CASCADE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引：加速查詢用戶的密碼歷史
CREATE INDEX IF NOT EXISTS idx_password_history_user
ON password_history(user_secure_code, created_at DESC);

-- 欄位註解
COMMENT ON TABLE password_history IS '密碼歷史記錄（用於防止重複使用密碼）';
COMMENT ON COLUMN password_history.user_secure_code IS '用戶 secure_code';
COMMENT ON COLUMN password_history.password_hash IS 'bcrypt hash';
COMMENT ON COLUMN password_history.created_at IS '建立時間';

-- 用戶表新增登入失敗追蹤欄位
ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INT DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_failed_login TIMESTAMP;

COMMENT ON COLUMN users.failed_login_count IS '連續登入失敗次數';
COMMENT ON COLUMN users.locked_until IS '帳號鎖定到期時間';
COMMENT ON COLUMN users.last_failed_login IS '最後一次登入失敗時間';
