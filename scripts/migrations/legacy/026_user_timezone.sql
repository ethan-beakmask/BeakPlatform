-- 026: 用戶個人時區
-- NULL 表示跟隨企業設定

ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(50);

COMMENT ON COLUMN users.timezone IS '個人時區 (IANA)，NULL 則跟隨企業設定';
