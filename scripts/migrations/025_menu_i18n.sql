-- 025: 選單多語系支援
-- 新增英文和簡體中文標題欄位

ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS title_en VARCHAR(100);
ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS title_zh_cn VARCHAR(100);

COMMENT ON COLUMN menu_items.title_en IS '英文標題';
COMMENT ON COLUMN menu_items.title_zh_cn IS '簡體中文標題';
