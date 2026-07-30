-- 089: Portal row-level ownership scope
-- 日期: 2026-07-30
-- 用途: 讓 NoCode portal 業務表視圖可宣告列級擁有權範圍，預設只看自己的列。

BEGIN;

ALTER TABLE dc_crud_views
  ADD COLUMN IF NOT EXISTS row_owner_scope VARCHAR(8) NOT NULL DEFAULT 'own';

COMMIT;
