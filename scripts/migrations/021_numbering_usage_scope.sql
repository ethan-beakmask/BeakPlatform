-- 021_numbering_usage_scope.sql
-- 編號規則使用範圍
-- 用於區分內部專用、外部專用、內部通用編號

-- 新增使用範圍欄位
ALTER TABLE user_numbering_rules
ADD COLUMN IF NOT EXISTS usage_scope VARCHAR(20) DEFAULT 'INTERNAL_ONLY' NOT NULL;

-- 欄位註解
COMMENT ON COLUMN user_numbering_rules.usage_scope IS '使用範圍: INTERNAL_ONLY=內部專用, EXTERNAL_ONLY=外部專用, INTERNAL_UNIVERSAL=內部通用';

-- 更新現有規則為內部專用（員工編號預設值）
UPDATE user_numbering_rules
SET usage_scope = 'INTERNAL_ONLY'
WHERE usage_scope IS NULL;

-- 驗證
SELECT 'user_numbering_rules.usage_scope' as field,
       COUNT(*) as total,
       COUNT(CASE WHEN usage_scope = 'INTERNAL_ONLY' THEN 1 END) as internal_only,
       COUNT(CASE WHEN usage_scope = 'EXTERNAL_ONLY' THEN 1 END) as external_only,
       COUNT(CASE WHEN usage_scope = 'INTERNAL_UNIVERSAL' THEN 1 END) as internal_universal
FROM user_numbering_rules;
