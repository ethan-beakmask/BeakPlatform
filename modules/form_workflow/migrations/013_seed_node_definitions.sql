-- 013: Seed workflow_node_definitions（完整初始資料）
-- 問題: install.sh 全新部署時，db.create_all() 建立空表，
--       007 migration 全為 UPDATE（0 筆命中），導致只剩 011/038 INSERT 的 3 筆。
--       流程設計器左側面板只顯示 [通知機制] 和 [系統整合]。
-- 修正: 用 INSERT ... ON CONFLICT (node_type) DO NOTHING 冪等補齊全部節點。
--
-- 執行方式: 由 run_migrations.py 自動執行

BEGIN;

-- =====================================================================
-- 基本
-- =====================================================================

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'Start', TRUE, 'SYSTEM', '基本', '開始', '流程的起點',
    '/static/modules/form_workflow/icons/workflow/start.svg',
    'modules.form_workflow.services.node_handlers.start_handler.StartHandler',
    '{}',
    'ellipse', '#22C55E', 80, 80,
    0, 1, 30, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'End', TRUE, 'SYSTEM', '基本', '結束', '流程的終點',
    '/static/modules/form_workflow/icons/workflow/end.svg',
    'modules.form_workflow.services.node_handlers.end_handler.EndHandler',
    '{}',
    'ellipse', '#EF4444', 80, 80,
    -1, 0, 30, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

-- =====================================================================
-- 表單
-- =====================================================================

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'FormAdapter', TRUE, 'SYSTEM', '表單', '簽核', '表單簽核節點',
    '/static/modules/form_workflow/icons/workflow/formadapter.svg',
    'modules.form_workflow.services.node_handlers.formadapter_handler.FormAdapterHandler',
    '{"approvalMode": "string", "assigneeType": "string", "assigneeValue": "string"}',
    'roundrectangle', '#0EA5E9', 140, 70,
    1, 2, 172800, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

-- =====================================================================
-- 控制
-- =====================================================================

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'Delay', TRUE, 'SYSTEM', '控制', '暫停', '延遲執行指定時間',
    '/static/modules/form_workflow/icons/workflow/delay.svg',
    'modules.form_workflow.services.node_handlers.delay_handler.DelayHandler',
    '{"delay_seconds": "number"}',
    'roundrectangle', '#64748B', 120, 60,
    1, 1, 86400, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'Branch', TRUE, 'SYSTEM', '控制', '分支', '根據條件選擇路徑',
    '/static/modules/form_workflow/icons/workflow/branch.svg',
    'modules.form_workflow.services.node_handlers.branch_handler.BranchHandler',
    '{}',
    'diamond', '#F59E0B', 100, 100,
    1, -1, 60, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'Condition', TRUE, 'SYSTEM', '控制', '條件判斷', '條件判斷節點',
    '/static/modules/form_workflow/icons/workflow/condition.svg',
    'modules.form_workflow.services.node_handlers.condition_handler.ConditionHandler',
    '{}',
    'diamond', '#8B5CF6', 100, 100,
    1, -1, 60, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'Switch', TRUE, 'SYSTEM', '控制', '條件分支', '多路條件判斷分支',
    '/static/modules/form_workflow/icons/workflow/switch.svg',
    'modules.form_workflow.services.node_handlers.switch_handler.SwitchHandler',
    '{}',
    'diamond', '#8B5CF6', 100, 100,
    1, -1, 60, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'Converge', TRUE, 'SYSTEM', '控制', '匯合', '等待多條路徑匯合',
    '/static/modules/form_workflow/icons/workflow/converge.svg',
    'modules.form_workflow.services.node_handlers.converge_handler.ConvergeHandler',
    '{"mode": "string"}',
    'diamond', '#6366F1', 100, 100,
    -1, 1, 60, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'ParallelFork', TRUE, 'SYSTEM', '控制', '並行分支', '並行執行多路分支',
    '/static/modules/form_workflow/icons/workflow/parallelfork.svg',
    'modules.form_workflow.services.node_handlers.parallelfork_handler.ParallelForkHandler',
    '{}',
    'diamond', '#F59E0B', 100, 100,
    1, -1, 60, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'ParallelJoin', TRUE, 'SYSTEM', '控制', '並行匯合', '等待所有並行分支完成',
    '/static/modules/form_workflow/icons/workflow/paralleljoin.svg',
    'modules.form_workflow.services.node_handlers.paralleljoin_handler.ParallelJoinHandler',
    '{"mode": "string"}',
    'diamond', '#6366F1', 100, 100,
    -1, 1, 3600, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'SubFlow', TRUE, 'SYSTEM', '控制', '子流程', '呼叫其他工作流程',
    '/static/modules/form_workflow/icons/workflow/subflow.svg',
    'modules.form_workflow.services.node_handlers.subflow_handler.SubFlowHandler',
    '{"childFlowId": "string"}',
    'roundrectangle', '#0EA5E9', 120, 60,
    1, 1, 3600, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

-- =====================================================================
-- 通知
-- =====================================================================

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'Telegram', TRUE, 'SYSTEM', '通知', 'Telegram 通知', '發送 Telegram 訊息',
    '/static/modules/form_workflow/icons/workflow/telegram.svg',
    'modules.form_workflow.services.node_handlers.telegram_handler.TelegramHandler',
    '{"chat_id": "string", "message": "string"}',
    'roundrectangle', '#0088CC', 120, 60,
    1, 1, 120, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'EmailAdapter', TRUE, 'SYSTEM', '通知', 'Email 通知', '發送 Email',
    '/static/modules/form_workflow/icons/workflow/emailadapter.svg',
    'modules.form_workflow.services.node_handlers.emailadapter_handler.EmailAdapterHandler',
    '{"to": "string", "body": "string", "subject": "string"}',
    'roundrectangle', '#3B82F6', 120, 60,
    -1, -1, 120, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'NavbarBroadcast', TRUE, 'SYSTEM', '通知', '跑馬燈廣播',
    '在 Navbar 顯示跑馬燈訊息，支援啟動/停止兩種模式',
    '/static/modules/form_workflow/icons/workflow/navbarbroadcast.svg',
    'modules.form_workflow.services.node_handlers.navbar_broadcast_handler.NavbarBroadcastHandler',
    '{"mode": "string", "message": "string", "bg_color": "string", "text_color": "string", "broadcast_code": "string", "display_seconds": "number", "duration_minutes": "number"}',
    'roundrectangle', '#3B82F6', 120, 60,
    -1, -1, 120, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'AlertBroadcast', TRUE, 'SYSTEM', '通知', '緊急廣播',
    '全頁強制彈窗，用戶必須確認已讀才能關閉',
    '/static/modules/form_workflow/icons/workflow/alertbroadcast.svg',
    'modules.form_workflow.services.node_handlers.alert_broadcast_handler.AlertBroadcastHandler',
    '{"title": "string", "message": "string", "require_ack": "boolean", "target_type": "string", "target_roles": "array", "broadcast_code": "string", "target_departments": "array"}',
    'roundrectangle', '#3B82F6', 120, 60,
    -1, -1, 120, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

-- =====================================================================
-- 變數
-- =====================================================================

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'OpSet', TRUE, 'SYSTEM', '變數', '設定變數', '設定流程變數值',
    '/static/modules/form_workflow/icons/workflow/opset.svg',
    'modules.form_workflow.services.node_handlers.opset_handler.OpSetHandler',
    '{"variables": "array"}',
    'roundrectangle', '#3B82F6', 120, 60,
    1, 1, 60, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'OpFieldRead', TRUE, 'SYSTEM', '變數', '讀取欄位', '從表單讀取欄位到變數',
    '/static/modules/form_workflow/icons/workflow/opfieldread.svg',
    'modules.form_workflow.services.node_handlers.opfieldread_handler.OpFieldReadHandler',
    '{"mappings": "array"}',
    'roundrectangle', '#14B8A6', 120, 60,
    1, 1, 60, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'OpFieldWrite', TRUE, 'SYSTEM', '變數', '寫入欄位', '將變數寫入表單欄位',
    '/static/modules/form_workflow/icons/workflow/opfieldwrite.svg',
    'modules.form_workflow.services.node_handlers.opfieldwrite_handler.OpFieldWriteHandler',
    '{"mappings": "array"}',
    'roundrectangle', '#06B6D4', 120, 60,
    1, 1, 60, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

-- =====================================================================
-- 整合
-- =====================================================================

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'EmailRelay', TRUE, 'SYSTEM', '整合', 'Email 轉發', '透過外部系統發送 Email',
    '/static/modules/form_workflow/icons/workflow/emailrelay.svg',
    'modules.form_workflow.services.node_handlers.emailrelay_handler.EmailRelayHandler',
    '{"to": "string", "body": "string", "subject": "string"}',
    'roundrectangle', '#EA580C', 120, 60,
    1, 1, 300, 3600,
    TRUE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'SqlExecutor', TRUE, 'SYSTEM', '整合', 'SQL 執行', '執行 SQL 查詢',
    '/static/modules/form_workflow/icons/workflow/sqlexecutor.svg',
    'modules.form_workflow.services.node_handlers.sqlexecutor_handler.SqlExecutorHandler',
    '{"sql": "string", "connection": "string"}',
    'roundrectangle', '#DC2626', 120, 60,
    1, 1, 300, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'SubSystemProvision', TRUE, 'SYSTEM', '整合', '子系統配置',
    '建立、停用或刪除子系統（含選單、開發者權限）',
    '/static/modules/form_workflow/icons/workflow/subsystemprovision.svg',
    'modules.form_workflow.services.node_handlers.sub_system_provision_handler.SubSystemProvisionHandler',
    '{"type": "object", "required": ["action"], "properties": {"action": {"enum": ["create", "suspend", "delete"], "type": "string", "description": "動作類型"}, "sub_system_code": {"type": "string", "description": "目標子系統 code（suspend/delete 用，支援變數替換）"}, "sub_system_icon": {"type": "string", "description": "圖示 class（optional，如 bi-box-seam）"}, "sub_system_name": {"type": "string", "description": "子系統名稱（支援變數替換，如 ${f.sub_system_name}）"}, "sub_system_developer": {"type": "string", "description": "開發者 user secure_code（支援變數替換，如 ${f.sub_system_developer}）"}}}',
    'roundrectangle', '#8B5CF6', 180, 50,
    10, 10, 300, 600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

-- =====================================================================
-- 系統
-- =====================================================================

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'SysTelegram', TRUE, 'SYSTEM', '系統', '系統 Telegram', '系統級 Telegram 通知',
    '/static/modules/form_workflow/icons/workflow/systelegram.svg',
    'modules.form_workflow.services.node_handlers.systelegram_handler.SysTelegramHandler',
    '{"message": "string"}',
    'roundrectangle', '#7C3AED', 120, 60,
    1, 1, 120, 3600,
    TRUE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

INSERT INTO workflow_node_definitions (
    secure_code, node_type, is_active, scope, category, display_name, description, icon,
    execution_handler, config_schema,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    require_system_admin, is_deleted, created_at, updated_at
) VALUES (
    encode(gen_random_bytes(16), 'hex'),
    'Abandon', TRUE, 'SYSTEM', '系統', '中止', '強制中止流程',
    '/static/modules/form_workflow/icons/workflow/abandon.svg',
    'modules.form_workflow.services.node_handlers.abandon_handler.AbandonHandler',
    '{}',
    'roundrectangle', '#991B1B', 120, 60,
    1, 0, 30, 3600,
    FALSE, FALSE, NOW(), NOW()
) ON CONFLICT (node_type) DO NOTHING;

COMMIT;
