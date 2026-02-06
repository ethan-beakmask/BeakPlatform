-- 027: 選單標題 JSONB 多語系
-- 新增 title_i18n JSONB 欄位，並將舊欄位資料遷移過去
-- 舊欄位 (title_en, title_zh_cn) 暫時保留向下相容

ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS title_i18n JSONB DEFAULT '{}';

COMMENT ON COLUMN menu_items.title_i18n IS '多語系標題 JSONB {"en": "...", "zh-CN": "...", "ja": "..."}';

-- 將現有 title_en, title_zh_cn 資料遷移到 title_i18n
UPDATE menu_items
SET title_i18n = jsonb_strip_nulls(jsonb_build_object(
    'en', NULLIF(title_en, ''),
    'zh-CN', NULLIF(title_zh_cn, '')
))
WHERE (title_en IS NOT NULL AND title_en != '')
   OR (title_zh_cn IS NOT NULL AND title_zh_cn != '');
