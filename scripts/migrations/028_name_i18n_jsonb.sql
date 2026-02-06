-- 028: 多 Model name_i18n JSONB 多語系
-- 為 job_titles, job_families, job_levels, approval_categories 新增 name_i18n 欄位
-- 並將 name_en 資料遷移過去

-- job_titles
ALTER TABLE job_titles ADD COLUMN IF NOT EXISTS name_i18n JSONB DEFAULT '{}';
COMMENT ON COLUMN job_titles.name_i18n IS '多語系名稱 JSONB {"en": "...", "zh-CN": "...", "ja": "..."}';

UPDATE job_titles
SET name_i18n = jsonb_strip_nulls(jsonb_build_object('en', NULLIF(name_en, '')))
WHERE name_en IS NOT NULL AND name_en != '';

-- job_families
ALTER TABLE job_families ADD COLUMN IF NOT EXISTS name_i18n JSONB DEFAULT '{}';
COMMENT ON COLUMN job_families.name_i18n IS '多語系名稱 JSONB {"en": "...", "zh-CN": "...", "ja": "..."}';

UPDATE job_families
SET name_i18n = jsonb_strip_nulls(jsonb_build_object('en', NULLIF(name_en, '')))
WHERE name_en IS NOT NULL AND name_en != '';

-- job_levels
ALTER TABLE job_levels ADD COLUMN IF NOT EXISTS name_i18n JSONB DEFAULT '{}';
COMMENT ON COLUMN job_levels.name_i18n IS '多語系名稱 JSONB {"en": "...", "zh-CN": "...", "ja": "..."}';

UPDATE job_levels
SET name_i18n = jsonb_strip_nulls(jsonb_build_object('en', NULLIF(name_en, '')))
WHERE name_en IS NOT NULL AND name_en != '';

-- approval_categories
ALTER TABLE approval_categories ADD COLUMN IF NOT EXISTS name_i18n JSONB DEFAULT '{}';
COMMENT ON COLUMN approval_categories.name_i18n IS '多語系名稱 JSONB {"en": "...", "zh-CN": "...", "ja": "..."}';

UPDATE approval_categories
SET name_i18n = jsonb_strip_nulls(jsonb_build_object('en', NULLIF(name_en, '')))
WHERE name_en IS NOT NULL AND name_en != '';
