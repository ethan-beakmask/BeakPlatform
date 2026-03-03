-- ============================================================================
-- 035_cleanup_org_lookup_data.sql
-- 軟刪除主庫中的企業級 lookup 資料
--
-- 企業級 lookup 已搬遷至企業專屬 DB (org_{id})，
-- 主庫中 org_secure_code IS NOT NULL 的資料為歷史殘留。
-- 本機資料皆為測試資料，軟刪除即可。
-- ============================================================================

BEGIN;

-- 軟刪除企業級 items
UPDATE lookup_items
SET is_deleted = TRUE, deleted_at = NOW()
WHERE org_secure_code IS NOT NULL
  AND is_deleted = FALSE;

-- 軟刪除企業級 categories
UPDATE lookup_categories
SET is_deleted = TRUE, deleted_at = NOW()
WHERE org_secure_code IS NOT NULL
  AND is_deleted = FALSE;

COMMIT;
