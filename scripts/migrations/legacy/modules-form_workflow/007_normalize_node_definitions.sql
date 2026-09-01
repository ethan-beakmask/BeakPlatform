-- 007: Node Type 定義正規化 - DB 成為 Single Source of Truth
-- Issue #10: 消除 API 硬編碼，讓 DB 驅動節點定義
--
-- 變更內容:
-- 1. node_type: ALL_CAPS → PascalCase (配合 API/JS/graph JSON)
-- 2. category: English → 中文 (配合前端 category_map)
-- 3. icon: 修正路徑至 /static/modules/form_workflow/icons/workflow/
-- 4. display_name: 統一配合 API hardcode
-- 5. description: 從 API hardcode 補齊
-- 6. config_schema: 從 API hardcode 補齊 (目前 21 筆 NULL)
-- 7. execution_handler: 統一為 modules.form_workflow.services.node_handlers.* 路徑
-- 8. require_system_admin: SysTelegram 改為 true
-- 9. icon 欄位長度: ALTER VARCHAR(100) → VARCHAR(200)
--
-- 執行方式: sudo -u postgres psql -d beakplatform_dev -f 007_normalize_node_definitions.sql

BEGIN;

-- 先擴大 icon 欄位長度
ALTER TABLE workflow_node_definitions ALTER COLUMN icon TYPE VARCHAR(200);

-- 暫時移除 node_type 的 UNIQUE 約束（因為要逐筆更新，可能有暫時衝突）
ALTER TABLE workflow_node_definitions DROP CONSTRAINT IF EXISTS workflow_node_definitions_node_type_key;

-- =====================================================================
-- 基本
-- =====================================================================

UPDATE workflow_node_definitions SET
    node_type = 'Start',
    category = '基本',
    display_name = '開始',
    description = '流程的起點',
    icon = '/bp/static/modules/form_workflow/icons/workflow/start.svg',
    config_schema = '{}',
    execution_handler = 'modules.form_workflow.services.node_handlers.start_handler.StartHandler',
    require_system_admin = false
WHERE node_type = 'START';

UPDATE workflow_node_definitions SET
    node_type = 'End',
    category = '基本',
    display_name = '結束',
    description = '流程的終點',
    icon = '/bp/static/modules/form_workflow/icons/workflow/end.svg',
    config_schema = '{}',
    execution_handler = 'modules.form_workflow.services.node_handlers.end_handler.EndHandler',
    require_system_admin = false
WHERE node_type = 'END';

-- =====================================================================
-- 表單 / 簽核
-- =====================================================================

UPDATE workflow_node_definitions SET
    node_type = 'FormAdapter',
    category = '表單',
    display_name = '簽核',
    description = '表單簽核節點',
    icon = '/bp/static/modules/form_workflow/icons/workflow/formadapter.svg',
    config_schema = '{"assigneeType": "string", "assigneeValue": "string", "approvalMode": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.formadapter_handler.FormAdapterHandler',
    require_system_admin = false
WHERE node_type = 'FORMADAPTER';

-- =====================================================================
-- 流程控制
-- =====================================================================

UPDATE workflow_node_definitions SET
    node_type = 'Delay',
    category = '控制',
    display_name = '暫停',
    description = '延遲執行指定時間',
    icon = '/bp/static/modules/form_workflow/icons/workflow/delay.svg',
    config_schema = '{"delay_seconds": "number"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.delay_handler.DelayHandler',
    require_system_admin = false
WHERE node_type = 'DELAY';

UPDATE workflow_node_definitions SET
    node_type = 'Branch',
    category = '控制',
    display_name = '分支',
    description = '根據條件選擇路徑',
    icon = '/bp/static/modules/form_workflow/icons/workflow/branch.svg',
    config_schema = '{}',
    execution_handler = 'modules.form_workflow.services.node_handlers.branch_handler.BranchHandler',
    require_system_admin = false
WHERE node_type = 'BRANCH';

UPDATE workflow_node_definitions SET
    node_type = 'Condition',
    category = '控制',
    display_name = '條件判斷',
    description = '條件判斷節點',
    icon = '/bp/static/modules/form_workflow/icons/workflow/condition.svg',
    config_schema = '{}',
    execution_handler = 'modules.form_workflow.services.node_handlers.condition_handler.ConditionHandler',
    require_system_admin = false
WHERE node_type = 'CONDITION';

UPDATE workflow_node_definitions SET
    node_type = 'Switch',
    category = '控制',
    display_name = '條件分支',
    description = '多路條件判斷分支',
    icon = '/bp/static/modules/form_workflow/icons/workflow/switch.svg',
    config_schema = '{}',
    execution_handler = 'modules.form_workflow.services.node_handlers.switch_handler.SwitchHandler',
    require_system_admin = false
WHERE node_type = 'SWITCH';

UPDATE workflow_node_definitions SET
    node_type = 'Converge',
    category = '控制',
    display_name = '匯合',
    description = '等待多條路徑匯合',
    icon = '/bp/static/modules/form_workflow/icons/workflow/converge.svg',
    config_schema = '{"mode": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.converge_handler.ConvergeHandler',
    require_system_admin = false
WHERE node_type = 'CONVERGE';

UPDATE workflow_node_definitions SET
    node_type = 'ParallelFork',
    category = '控制',
    display_name = '並行分支',
    description = '並行執行多路分支',
    icon = '/bp/static/modules/form_workflow/icons/workflow/parallelfork.svg',
    config_schema = '{}',
    execution_handler = 'modules.form_workflow.services.node_handlers.parallelfork_handler.ParallelForkHandler',
    require_system_admin = false
WHERE node_type = 'PARALLEL_FORK';

UPDATE workflow_node_definitions SET
    node_type = 'ParallelJoin',
    category = '控制',
    display_name = '並行匯合',
    description = '等待所有並行分支完成',
    icon = '/bp/static/modules/form_workflow/icons/workflow/paralleljoin.svg',
    config_schema = '{"mode": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.paralleljoin_handler.ParallelJoinHandler',
    require_system_admin = false
WHERE node_type = 'PARALLEL_JOIN';

UPDATE workflow_node_definitions SET
    node_type = 'SubFlow',
    category = '控制',
    display_name = '子流程',
    description = '呼叫其他工作流程',
    icon = '/bp/static/modules/form_workflow/icons/workflow/subflow.svg',
    config_schema = '{"childFlowId": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.subflow_handler.SubFlowHandler',
    require_system_admin = false
WHERE node_type = 'SUBFLOW';

-- =====================================================================
-- 通知
-- =====================================================================

UPDATE workflow_node_definitions SET
    node_type = 'Notification',
    category = '通知',
    display_name = '通知',
    description = '系統內部通知',
    icon = '/bp/static/modules/form_workflow/icons/workflow/notification.svg',
    config_schema = '{"message": "string", "notifyType": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.notification_handler.NotificationHandler',
    require_system_admin = false
WHERE node_type = 'NOTIFICATION';

UPDATE workflow_node_definitions SET
    node_type = 'Telegram',
    category = '通知',
    display_name = 'Telegram 通知',
    description = '發送 Telegram 訊息',
    icon = '/bp/static/modules/form_workflow/icons/workflow/telegram.svg',
    config_schema = '{"message": "string", "chat_id": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.telegram_handler.TelegramHandler',
    require_system_admin = false
WHERE node_type = 'TELEGRAM';

UPDATE workflow_node_definitions SET
    node_type = 'EmailAdapter',
    category = '通知',
    display_name = 'Email 通知',
    description = '發送 Email',
    icon = '/bp/static/modules/form_workflow/icons/workflow/emailadapter.svg',
    config_schema = '{"to": "string", "subject": "string", "body": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.emailadapter_handler.EmailAdapterHandler',
    require_system_admin = false
WHERE node_type = 'EMAILADAPTER';

-- =====================================================================
-- 變數 / 資料操作
-- =====================================================================

UPDATE workflow_node_definitions SET
    node_type = 'OpSet',
    category = '變數',
    display_name = '設定變數',
    description = '設定流程變數值',
    icon = '/bp/static/modules/form_workflow/icons/workflow/opset.svg',
    config_schema = '{"variables": "array"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.opset_handler.OpSetHandler',
    require_system_admin = false
WHERE node_type = 'OPSET';

UPDATE workflow_node_definitions SET
    node_type = 'OpFieldRead',
    category = '變數',
    display_name = '讀取欄位',
    description = '從表單讀取欄位到變數',
    icon = '/bp/static/modules/form_workflow/icons/workflow/opfieldread.svg',
    config_schema = '{"mappings": "array"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.opfieldread_handler.OpFieldReadHandler',
    require_system_admin = false
WHERE node_type = 'OP_FieldRead';

UPDATE workflow_node_definitions SET
    node_type = 'OpFieldWrite',
    category = '變數',
    display_name = '寫入欄位',
    description = '將變數寫入表單欄位',
    icon = '/bp/static/modules/form_workflow/icons/workflow/opfieldwrite.svg',
    config_schema = '{"mappings": "array"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.opfieldwrite_handler.OpFieldWriteHandler',
    require_system_admin = false
WHERE node_type = 'OP_FieldWrite';

UPDATE workflow_node_definitions SET
    node_type = 'FormExp',
    category = '變數',
    display_name = '表單匯出',
    description = '將表單資料匯出',
    icon = '/bp/static/modules/form_workflow/icons/workflow/formexp.svg',
    config_schema = '{}',
    execution_handler = 'modules.form_workflow.services.node_handlers.formexp_handler.FormExpHandler',
    require_system_admin = false
WHERE node_type = 'FORMEXP';

-- =====================================================================
-- 外部整合
-- =====================================================================

UPDATE workflow_node_definitions SET
    node_type = 'EmailRelay',
    category = '整合',
    display_name = 'Email 轉發',
    description = '透過外部系統發送 Email',
    icon = '/bp/static/modules/form_workflow/icons/workflow/emailrelay.svg',
    config_schema = '{"to": "string", "subject": "string", "body": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.emailrelay_handler.EmailRelayHandler',
    require_system_admin = false
WHERE node_type = 'EMAILRELAY';

UPDATE workflow_node_definitions SET
    node_type = 'SqlExecutor',
    category = '整合',
    display_name = 'SQL 執行',
    description = '執行 SQL 查詢',
    icon = '/bp/static/modules/form_workflow/icons/workflow/sqlexecutor.svg',
    config_schema = '{"sql": "string", "connection": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.sqlexecutor_handler.SqlExecutorHandler',
    require_system_admin = false
WHERE node_type = 'SQLEXECUTOR';

-- =====================================================================
-- 系統
-- =====================================================================

UPDATE workflow_node_definitions SET
    node_type = 'SysTelegram',
    category = '系統',
    display_name = '系統 Telegram',
    description = '系統級 Telegram 通知',
    icon = '/bp/static/modules/form_workflow/icons/workflow/systelegram.svg',
    config_schema = '{"message": "string"}',
    execution_handler = 'modules.form_workflow.services.node_handlers.systelegram_handler.SysTelegramHandler',
    require_system_admin = true
WHERE node_type = 'SYS_TELEGRAM';

UPDATE workflow_node_definitions SET
    node_type = 'Abandon',
    category = '系統',
    display_name = '中止',
    description = '強制中止流程',
    icon = '/bp/static/modules/form_workflow/icons/workflow/abandon.svg',
    config_schema = '{}',
    execution_handler = 'modules.form_workflow.services.node_handlers.abandon_handler.AbandonHandler',
    require_system_admin = false
WHERE node_type = 'ABANDON';

-- 重新加回 UNIQUE 約束
ALTER TABLE workflow_node_definitions ADD CONSTRAINT workflow_node_definitions_node_type_key UNIQUE (node_type);

COMMIT;
