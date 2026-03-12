-- 004_page_layout_status.sql
-- dc_page_layouts 加入 status 欄位 (draft / published)

BEGIN;

ALTER TABLE dc_page_layouts
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'draft';

COMMIT;
