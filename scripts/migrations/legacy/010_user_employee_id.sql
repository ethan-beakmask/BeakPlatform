-- Migration 010: User Employee ID
-- 用戶企業成員編號欄位
-- 2025-12-25

-- 新增企業成員編號欄位 (組織內唯一)
ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_id VARCHAR(50);

-- 企業成員編號在同一企業內唯一
CREATE UNIQUE INDEX IF NOT EXISTS unique_employee_id_org
ON users (employee_id, org_secure_code)
WHERE employee_id IS NOT NULL AND is_deleted = false;

-- 欄位註解
COMMENT ON COLUMN users.employee_id IS '企業成員編號 (組織內唯一)';
