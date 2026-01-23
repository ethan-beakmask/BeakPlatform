-- 編號規則雙預設支援
-- 將 is_default (布林) 改為 default_for (字串)
-- 支援 EMPLOYEE（員工編號預設）和 EXTERNAL（外部人員預設）

-- 1. 新增 default_for 欄位
ALTER TABLE user_numbering_rules
ADD COLUMN IF NOT EXISTS default_for VARCHAR(20) NULL;

COMMENT ON COLUMN user_numbering_rules.default_for IS '預設用途: EMPLOYEE=員工預設, EXTERNAL=外部人員預設, NULL=非預設';

-- 2. 遷移現有資料：原本 is_default=true 的設為 EMPLOYEE（員工預設）
UPDATE user_numbering_rules
SET default_for = 'EMPLOYEE'
WHERE is_default = true;

-- 3. 移除舊的 is_default 欄位
ALTER TABLE user_numbering_rules
DROP COLUMN IF EXISTS is_default;

-- 完成
SELECT 'Migration 010: numbering default_for completed' AS status;
