-- 009_user_personal_fields.sql
-- 用戶個人資料欄位
-- 執行日期: 2025-12-25

-- 新增用戶個人資料欄位
ALTER TABLE users ADD COLUMN IF NOT EXISTS english_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS native_name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS nickname VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS backup_email_1 VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS backup_email_2 VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_phone_1 VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_phone_2 VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS interface_language VARCHAR(10);

-- 欄位註解
COMMENT ON COLUMN users.english_name IS '英文姓名';
COMMENT ON COLUMN users.native_name IS '本國姓名';
COMMENT ON COLUMN users.nickname IS '暱稱';
COMMENT ON COLUMN users.backup_email_1 IS '備用 Email 1';
COMMENT ON COLUMN users.backup_email_2 IS '備用 Email 2';
COMMENT ON COLUMN users.mobile_phone_1 IS '手機號碼 1';
COMMENT ON COLUMN users.mobile_phone_2 IS '手機號碼 2';
COMMENT ON COLUMN users.interface_language IS '介面語言 (覆蓋企業設定)';

-- 完成
SELECT '009_user_personal_fields.sql 執行完成' AS status;
