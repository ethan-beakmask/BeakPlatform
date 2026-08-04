-- 091: DcPageTemplate source subsystem marker
-- 日期: 2026-08-04
-- 用途: 記錄頁面樣板來源子系統，供套用樣板時判斷是否需要淨化外部引用。

BEGIN;

ALTER TABLE dc_page_templates
  ADD COLUMN IF NOT EXISTS source_sub_system_sc VARCHAR(32);

COMMIT;
