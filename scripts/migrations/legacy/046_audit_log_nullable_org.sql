-- 046: audit_logs.org_secure_code 改為 nullable
-- 目的: 允許記錄未知網域的登入失敗（此時無法對應任何企業）
-- 影響: 僅 audit_logs 表，不影響其他表的企業隔離

ALTER TABLE audit_logs ALTER COLUMN org_secure_code DROP NOT NULL;

COMMENT ON COLUMN audit_logs.org_secure_code IS '企業代碼 (NULL 表示無法對應企業，如未知網域登入)';
