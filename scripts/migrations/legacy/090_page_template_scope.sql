-- 090: DcPageTemplate scope support
-- 日期: 2026-08-04
-- 用途: 讓頁面樣板支援平台內建、企業共用、子系統私有三種範圍。

BEGIN;

ALTER TABLE dc_page_templates
  ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'org';

ALTER TABLE dc_page_templates
  ADD COLUMN IF NOT EXISTS sub_system_secure_code VARCHAR(32);

ALTER TABLE dc_page_templates
  ALTER COLUMN org_secure_code DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dc_page_templates_scope
  ON dc_page_templates(scope)
  WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS idx_dc_page_templates_sub_system_secure_code
  ON dc_page_templates(sub_system_secure_code)
  WHERE is_deleted = false;

ALTER TABLE dc_page_templates
  DROP CONSTRAINT IF EXISTS ck_dc_page_templates_scope;

ALTER TABLE dc_page_templates
  ADD CONSTRAINT ck_dc_page_templates_scope CHECK (
      (scope = 'system'     AND org_secure_code IS NULL     AND sub_system_secure_code IS NULL)
   OR (scope = 'org'        AND org_secure_code IS NOT NULL AND sub_system_secure_code IS NULL)
   OR (scope = 'sub_system' AND org_secure_code IS NOT NULL AND sub_system_secure_code IS NOT NULL)
  );

COMMIT;
