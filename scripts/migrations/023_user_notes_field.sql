-- 023_user_notes_field.sql
-- 新增用戶備註欄位（用於外部廠商等）

ALTER TABLE users
ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT NULL;

COMMENT ON COLUMN users.notes IS '用戶備註（管理員可見）';

SELECT '用戶備註欄位已新增' AS message;
