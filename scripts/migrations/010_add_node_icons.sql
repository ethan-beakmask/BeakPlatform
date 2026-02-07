-- ============================================================
-- BeakPlatform 資料庫遷移腳本
-- 版本: 010
-- 描述: 新增節點定義圖示 (SVG 檔案路徑)
-- 日期: 2026-01-18
-- ============================================================

BEGIN;

-- 更新節點圖示
-- 使用本地 SVG 檔案 (源自 Remix Icon, Apache 2.0 License)
-- 路徑: /static/icons/workflow/*.svg

-- 流程控制 (FLOW_CONTROL)
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/start.svg' WHERE node_type = 'START';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/end.svg' WHERE node_type = 'END';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/condition.svg' WHERE node_type = 'CONDITION';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/branch.svg' WHERE node_type = 'BRANCH';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/switch.svg' WHERE node_type = 'SWITCH';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/parallel_fork.svg' WHERE node_type = 'PARALLEL_FORK';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/parallel_join.svg' WHERE node_type = 'PARALLEL_JOIN';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/converge.svg' WHERE node_type = 'CONVERGE';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/delay.svg' WHERE node_type = 'DELAY';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/subflow.svg' WHERE node_type = 'SUBFLOW';

-- 簽核 (APPROVAL)
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/approve.svg' WHERE node_type = 'APPROVE';

-- 通知 (NOTIFICATION)
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/notification.svg' WHERE node_type = 'NOTIFICATION';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/telegram.svg' WHERE node_type = 'TELEGRAM';

-- 資料操作 (DATA_OPERATION)
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/opset.svg' WHERE node_type = 'OPSET';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/formexp.svg' WHERE node_type = 'FORMEXP';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/fieldread.svg' WHERE node_type = 'OP_FieldRead';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/fieldwrite.svg' WHERE node_type = 'OP_FieldWrite';

-- 整合 (INTEGRATION)
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/emailrelay.svg' WHERE node_type = 'EMAILRELAY';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/sqlexecutor.svg' WHERE node_type = 'SQLEXECUTOR';

-- 系統 (SYSTEM)
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/abandon.svg' WHERE node_type = 'ABANDON';
UPDATE workflow_node_definitions SET icon = '/static/icons/workflow/sys_telegram.svg' WHERE node_type = 'SYS_TELEGRAM';

COMMIT;

-- 驗證
DO $$
DECLARE
    empty_icon_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO empty_icon_count
    FROM workflow_node_definitions
    WHERE icon IS NULL OR icon = '';

    IF empty_icon_count > 0 THEN
        RAISE WARNING '有 % 個節點尚未設定圖示', empty_icon_count;
    ELSE
        RAISE NOTICE '所有節點圖示已更新完成 (SVG 檔案)';
    END IF;
END $$;
