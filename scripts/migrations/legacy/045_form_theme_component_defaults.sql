-- 045: 表單風格主題 - 元件預設屬性
-- 2026-03-21

-- 加 component_defaults 欄位
ALTER TABLE fw_form_themes ADD COLUMN IF NOT EXISTS component_defaults JSONB;

-- 新增「建議平行」主題（標籤置左對齊）
INSERT INTO fw_form_themes (secure_code, name, display_name, description, component_defaults, is_system, is_active, sort_order,
    created_at, updated_at, is_deleted)
VALUES (
    'parallel-label-theme01',
    'parallel-label',
    '建議平行',
    '標籤置左對齊，寬度15%，邊距3%',
    '{"labelPosition": "left-left", "labelWidth": 15, "labelMargin": 3}'::jsonb,
    true,
    true,
    5,
    NOW(), NOW(), FALSE
)
ON CONFLICT DO NOTHING;
