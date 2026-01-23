-- Migration: 007_add_dept_roles.sql
-- 為現有企業新增副主管和代理人角色
-- 執行時間: 2025-12-30

-- 為每個企業新增 DEPT_DEPUTY（副主管）角色
INSERT INTO roles (secure_code, org_secure_code, role_type, scope_type, code, name, description, is_manager, is_system_role, is_active, full_path, level, sort_order, is_deleted, created_at, updated_at)
SELECT
    substr(md5(random()::text), 1, 22),
    o.secure_code,
    'POSITION',
    'DEPARTMENT',
    'DEPT_DEPUTY',
    '副主管',
    '部門副主管',
    true,
    true,
    true,
    '/POSITION/DEPARTMENT/DEPT_DEPUTY',
    3,
    2,
    false,
    NOW(),
    NOW()
FROM organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM roles r
    WHERE r.org_secure_code = o.secure_code
    AND r.code = 'DEPT_DEPUTY'
    AND r.is_deleted = false
);

-- 為每個企業新增 DEPT_PROXY1（代理人一）角色
INSERT INTO roles (secure_code, org_secure_code, role_type, scope_type, code, name, description, is_manager, is_system_role, is_active, full_path, level, sort_order, is_deleted, created_at, updated_at)
SELECT
    substr(md5(random()::text), 1, 22),
    o.secure_code,
    'POSITION',
    'DEPARTMENT',
    'DEPT_PROXY1',
    '代理人(一)',
    '部門代理人，主管不在時代為簽核',
    false,
    true,
    true,
    '/POSITION/DEPARTMENT/DEPT_PROXY1',
    3,
    3,
    false,
    NOW(),
    NOW()
FROM organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM roles r
    WHERE r.org_secure_code = o.secure_code
    AND r.code = 'DEPT_PROXY1'
    AND r.is_deleted = false
);

-- 為每個企業新增 DEPT_PROXY2（代理人二）角色
INSERT INTO roles (secure_code, org_secure_code, role_type, scope_type, code, name, description, is_manager, is_system_role, is_active, full_path, level, sort_order, is_deleted, created_at, updated_at)
SELECT
    substr(md5(random()::text), 1, 22),
    o.secure_code,
    'POSITION',
    'DEPARTMENT',
    'DEPT_PROXY2',
    '代理人(二)',
    '部門代理人，主管不在時代為簽核',
    false,
    true,
    true,
    '/POSITION/DEPARTMENT/DEPT_PROXY2',
    3,
    4,
    false,
    NOW(),
    NOW()
FROM organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM roles r
    WHERE r.org_secure_code = o.secure_code
    AND r.code = 'DEPT_PROXY2'
    AND r.is_deleted = false
);

-- 驗證
SELECT org_secure_code, code, name FROM roles
WHERE code IN ('DEPT_MANAGER', 'DEPT_DEPUTY', 'DEPT_PROXY1', 'DEPT_PROXY2')
AND is_deleted = false
ORDER BY org_secure_code, code;
