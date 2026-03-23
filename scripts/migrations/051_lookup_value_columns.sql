-- Migration 051: Lookup Items 多型別值欄位
-- 新增 value_str, value_int, value_decimal, value_date, value_time, value_datetime
-- 讓選項清單支援多種資料型態儲存

BEGIN;

ALTER TABLE lookup_items ADD COLUMN IF NOT EXISTS value_str VARCHAR(500);
ALTER TABLE lookup_items ADD COLUMN IF NOT EXISTS value_int BIGINT;
ALTER TABLE lookup_items ADD COLUMN IF NOT EXISTS value_decimal NUMERIC(20,2);
ALTER TABLE lookup_items ADD COLUMN IF NOT EXISTS value_date DATE;
ALTER TABLE lookup_items ADD COLUMN IF NOT EXISTS value_time TIME WITHOUT TIME ZONE;
ALTER TABLE lookup_items ADD COLUMN IF NOT EXISTS value_datetime TIMESTAMP WITHOUT TIME ZONE;

COMMENT ON COLUMN lookup_items.value_str IS '字串值 (最長500字元)';
COMMENT ON COLUMN lookup_items.value_int IS '整數值';
COMMENT ON COLUMN lookup_items.value_decimal IS '小數值 (2位小數)';
COMMENT ON COLUMN lookup_items.value_date IS '日期值';
COMMENT ON COLUMN lookup_items.value_time IS '時間值';
COMMENT ON COLUMN lookup_items.value_datetime IS '日期時間值';

COMMIT;
