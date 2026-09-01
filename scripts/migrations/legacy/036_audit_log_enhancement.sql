-- 036: 稽核日誌增強 + 審計等級設定
-- 新增 HTTP 請求相關欄位，供 after_request hook 自動記錄
-- 新增 audit_level 系統設定

BEGIN;

-- 1. audit_logs 加欄位
ALTER TABLE audit_logs
    ADD COLUMN IF NOT EXISTS request_method VARCHAR(10),
    ADD COLUMN IF NOT EXISTS request_path VARCHAR(500),
    ADD COLUMN IF NOT EXISTS status_code INTEGER;

-- 2. 建立索引
CREATE INDEX IF NOT EXISTS idx_audit_logs_method ON audit_logs (request_method);
CREATE INDEX IF NOT EXISTS idx_audit_logs_status ON audit_logs (status_code);

-- 3. 種子 audit_level 系統設定
INSERT INTO system_settings (secure_code, key, value, value_type, description, category, created_at, updated_at, is_deleted)
SELECT
    substr(md5(random()::text), 1, 32),
    'audit_level',
    'STANDARD',
    'string',
    '稽核記錄等級: MINIMAL(僅登入登出), STANDARD(登入登出+寫入操作), VERBOSE(全部請求)',
    'security',
    NOW(), NOW(), false
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'audit_level'
);

-- 4. 種子 audit_retention_days 系統設定
INSERT INTO system_settings (secure_code, key, value, value_type, description, category, created_at, updated_at, is_deleted)
SELECT
    substr(md5(random()::text), 1, 32),
    'audit_retention_days',
    '90',
    'integer',
    '稽核記錄保留天數 (超過自動清理)',
    'security',
    NOW(), NOW(), false
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'audit_retention_days'
);

COMMIT;
