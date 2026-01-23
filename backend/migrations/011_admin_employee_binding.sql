-- 011_admin_employee_binding.sql
-- 企業管理員綁定員工帳號
--
-- 功能：
-- 1. 新增 bound_employee_secure_code 欄位
-- 2. 一對一綁定：管理員 → 員工
-- 3. 當員工帳號停用/刪除時，關聯的管理員帳號也無法登入

-- 新增綁定欄位
ALTER TABLE users
ADD COLUMN IF NOT EXISTS bound_employee_secure_code VARCHAR(32) REFERENCES users(secure_code);

-- 唯一約束：一個員工只能被一個管理員綁定
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_bound_employee
ON users(bound_employee_secure_code)
WHERE bound_employee_secure_code IS NOT NULL;

-- 欄位註解
COMMENT ON COLUMN users.bound_employee_secure_code IS '企業管理員綁定的員工帳號 (一對一)';
