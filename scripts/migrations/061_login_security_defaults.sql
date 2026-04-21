-- 061: 登入安全欄位系統預設
-- 三欄位偽裝機制：sv_1/sv_2/sv_3 分別指定為密碼、地雷、救助

-- 員工登入預設
INSERT INTO system_settings (secure_code, key, value, value_type, description, category, updated_by, created_at, updated_at, is_deleted)
SELECT
    substr(md5(random()::text), 1, 32),
    'login_security_employee',
    '{"password_field": "sv_2", "mine_field": "sv_1", "rescue_field": "sv_3", "rescue_keyword": ""}',
    'json',
    '員工登入安全欄位預設（密碼/地雷/救助欄位配置）',
    'login_security',
    'MIGRATION',
    NOW(),
    NOW(),
    false
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'login_security_employee'
);

-- 廠商登入預設
INSERT INTO system_settings (secure_code, key, value, value_type, description, category, updated_by, created_at, updated_at, is_deleted)
SELECT
    substr(md5(random()::text), 1, 32),
    'login_security_vendor',
    '{"password_field": "sv_2", "mine_field": "sv_1", "rescue_field": "sv_3", "rescue_keyword": ""}',
    'json',
    '廠商登入安全欄位預設（密碼/地雷/救助欄位配置）',
    'login_security',
    'MIGRATION',
    NOW(),
    NOW(),
    false
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'login_security_vendor'
);
