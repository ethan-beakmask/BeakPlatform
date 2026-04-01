-- BeakPlatform RBAC Factory Defaults (install-only)
-- Generated: 2026-04-01 09:05 UTC
-- 
-- 安全機制: 只在 rbac_defaults 表為空時才插入
-- (upgrade 不會覆蓋用戶已儲存的預設值)

-- 條件: 僅當 rbac_defaults 表為空時執行
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM rbac_defaults LIMIT 1) THEN

        -- Role: FLOW_DESIGNER (3 permissions)
        INSERT INTO rbac_defaults (role_code, permission_code, saved_by, saved_at) VALUES ('FLOW_DESIGNER', 'form_workflow.design.tryout', 'factory_install', NOW());
        INSERT INTO rbac_defaults (role_code, permission_code, saved_by, saved_at) VALUES ('FLOW_DESIGNER', 'form_workflow.workflow.manage', 'factory_install', NOW());
        INSERT INTO rbac_defaults (role_code, permission_code, saved_by, saved_at) VALUES ('FLOW_DESIGNER', 'form_workflow.workflow.view', 'factory_install', NOW());

    END IF;
END $$;