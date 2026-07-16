-- 082: beluga 自訂角色 SOC_L1 收編為模組預設角色「資安人員」(SECURITY_STAFF)
--
-- 背景 (2026-07-16, 原子 4852):
--   open_defense 模組新增 default_roles 機制，模組預設角色為 SECURITY_STAFF/資安人員。
--   beluga 既有的手動自訂角色 SOC_L1 (SOCL1abc90a14db079b05b) 依用戶決策收編為
--   該模組預設角色，避免同企業出現 SOC_L1 + SECURITY_STAFF 兩個重疊角色。
--
-- 安全性:
--   - 角色 secure_code 不變，user_role_assignments (3 筆)、menu_role_requirements
--     (security_cases Key2)、workflow graph (以 secure_code 引用) 全部不受影響。
--   - 冪等：重跑無副作用。

UPDATE roles
SET code = 'SECURITY_STAFF',
    name = '資安人員',
    description = '資安案件處置中心值班與案件簽核人員（開放防禦模組預設角色）',
    role_level = 'MODULE',
    is_system_role = true,
    full_path = '/資安人員'
WHERE secure_code = 'SOCL1abc90a14db079b05b'
  AND code = 'SOC_L1';
