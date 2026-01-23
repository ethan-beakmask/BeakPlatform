-- 009_time_management_menu.sql
-- 時間管理選單項目
-- 建立日期: 2026-01-07

-- 產生 secure_code 函數（如果不存在）
CREATE OR REPLACE FUNCTION generate_secure_code()
RETURNS VARCHAR(24) AS $$
DECLARE
    chars TEXT := 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
    result TEXT := '';
    i INTEGER;
BEGIN
    FOR i IN 1..24 LOOP
        result := result || substr(chars, floor(random() * 64 + 1)::integer, 1);
    END LOOP;
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- 新增「時間設定」父選單
INSERT INTO menu_items (
    secure_code, org_secure_code, code, title, icon,
    link_type, link_target, open_in_new_tab, display_order, depth,
    is_expanded, is_active, required_level, is_shared,
    created_at, updated_at, is_deleted
)
SELECT
    generate_secure_code(),
    'system.local',
    'time_config',
    '時間設定',
    '⏰',
    'header',
    NULL,
    FALSE,
    210,  -- 在 jobs_config (205) 之後
    0,
    FALSE,
    TRUE,
    1,    -- 企業管理員
    TRUE, -- 系統共用選單
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM menu_items WHERE code = 'time_config' AND org_secure_code = 'system.local'
);

-- 取得 time_config 的 secure_code
DO $$
DECLARE
    v_parent_code VARCHAR(32);
BEGIN
    SELECT secure_code INTO v_parent_code
    FROM menu_items
    WHERE code = 'time_config' AND org_secure_code = 'system.local';

    -- 新增「基本班表」子選單
    INSERT INTO menu_items (
        secure_code, org_secure_code, code, title, icon,
        link_type, link_target, parent_secure_code, open_in_new_tab, display_order, depth,
        is_expanded, is_active, required_level, is_shared,
        created_at, updated_at, is_deleted
    )
    SELECT
        generate_secure_code(),
        'system.local',
        'work_schedules',
        '基本班表',
        '📅',
        'url',
        '/admin/settings/work-schedules',
        v_parent_code,
        FALSE,
        2101,
        1,
        FALSE,
        TRUE,
        1,    -- 企業管理員
        TRUE, -- 系統共用選單
        NOW(),
        NOW(),
        FALSE
    WHERE NOT EXISTS (
        SELECT 1 FROM menu_items WHERE code = 'work_schedules' AND org_secure_code = 'system.local'
    );
END $$;

-- 顯示結果
SELECT secure_code, code, title, link_target, parent_secure_code, display_order
FROM menu_items
WHERE code IN ('time_config', 'work_schedules') AND org_secure_code = 'system.local'
ORDER BY display_order;
