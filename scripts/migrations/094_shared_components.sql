-- 094: NoCode shared components
-- 日期: 2026-08-06
-- 用途: 泛化子系統層級共用元件，並將既有 dc_shared_menus 資料冪等搬遷。

BEGIN;

CREATE TABLE IF NOT EXISTS dc_shared_components (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    sub_system_secure_code VARCHAR(32) NOT NULL,
    name VARCHAR(200) NOT NULL,
    widget_type VARCHAR(32) NOT NULL,
    widget_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    deleted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dc_shared_components_sub_system_secure_code
  ON dc_shared_components(sub_system_secure_code);

CREATE INDEX IF NOT EXISTS idx_dc_shared_components_is_active
  ON dc_shared_components(is_active);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dc_shared_components_sub_system_name_active
  ON dc_shared_components(sub_system_secure_code, name)
  WHERE is_deleted = false;

INSERT INTO dc_shared_components (
    secure_code,
    org_secure_code,
    sub_system_secure_code,
    name,
    widget_type,
    widget_json,
    is_active,
    created_at,
    updated_at,
    is_deleted,
    deleted_at
)
SELECT
    m.secure_code,
    m.org_secure_code,
    m.sub_system_secure_code,
    m.name,
    'menu',
    jsonb_build_object('type', 'menu', 'items', m.items) || COALESCE(m.config, '{}'::jsonb),
    m.is_active,
    m.created_at,
    m.updated_at,
    m.is_deleted,
    m.deleted_at
FROM dc_shared_menus m
WHERE NOT EXISTS (
    SELECT 1
    FROM dc_shared_components c
    WHERE c.secure_code = m.secure_code
);

-- 舊 shared-menus API 只驗 items、不驗 config，因此 config.style.background_file
-- 允許存成空字串（UI 上的「不使用底圖」）。新 API 會驗整個 widget_json，
-- 而 schema 的 background_file 有 pattern，空字串會被擋成 400。
-- 這裡把既有空字串清掉，否則使用者一編輯舊共用選單就存不回去。冪等。
UPDATE dc_shared_components
SET widget_json = jsonb_set(widget_json, '{style}', (widget_json -> 'style') - 'background_file')
WHERE widget_type = 'menu'
  AND widget_json -> 'style' ? 'background_file'
  AND COALESCE(widget_json -> 'style' ->> 'background_file', '') = '';

COMMIT;
