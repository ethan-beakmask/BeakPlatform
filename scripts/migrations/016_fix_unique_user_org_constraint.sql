-- Migration 016: 修復 users 表的 unique 約束
-- 問題：原約束不排除已刪除記錄，導致軟刪除帳號無法被重新建立
-- 解法：改為 partial unique index，只檢查 is_deleted = false 的記錄

BEGIN;

-- 1. 修復 unique_user_org (username + org_secure_code)
ALTER TABLE users DROP CONSTRAINT IF EXISTS unique_user_org;
DROP INDEX IF EXISTS unique_user_org;

CREATE UNIQUE INDEX unique_user_org
ON users (username, org_secure_code)
WHERE is_deleted = false;

-- 2. 修復 ix_users_email (email 全域唯一)
DROP INDEX IF EXISTS ix_users_email;

CREATE UNIQUE INDEX ix_users_email
ON users (email)
WHERE is_deleted = false;

-- 確認結果
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = 'users' AND indexname IN ('unique_user_org', 'ix_users_email');

COMMIT;
