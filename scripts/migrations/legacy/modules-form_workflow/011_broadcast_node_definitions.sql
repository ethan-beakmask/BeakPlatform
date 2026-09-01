-- 011: 新增 NavbarBroadcast, AlertBroadcast 節點定義
-- 刪除舊的 FormExp, Notification（已過時）

DELETE FROM workflow_node_definitions WHERE node_type IN ('FormExp', 'Notification');

INSERT INTO workflow_node_definitions (
    secure_code, node_type, scope, category, display_name, description, icon,
    config_schema, execution_handler, require_system_admin,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    is_active, is_deleted, created_at, updated_at
)
SELECT
    encode(gen_random_bytes(16), 'hex'),
    'NavbarBroadcast', 'SYSTEM', '通知', '跑馬燈廣播',
    '在 Navbar 顯示跑馬燈訊息，支援啟動/停止兩種模式',
    '/static/modules/form_workflow/icons/workflow/navbarbroadcast.svg',
    '{"mode": "string", "broadcast_code": "string", "message": "string", "text_color": "string", "bg_color": "string", "display_seconds": "number", "duration_minutes": "number"}',
    'modules.form_workflow.services.node_handlers.navbar_broadcast_handler.NavbarBroadcastHandler',
    false,
    'roundrectangle', '#3B82F6', 120, 60,
    -1, -1, 120, 3600,
    true, false, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM workflow_node_definitions WHERE node_type = 'NavbarBroadcast');

INSERT INTO workflow_node_definitions (
    secure_code, node_type, scope, category, display_name, description, icon,
    config_schema, execution_handler, require_system_admin,
    canvas_shape, canvas_color, canvas_width, canvas_height,
    max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds,
    is_active, is_deleted, created_at, updated_at
)
SELECT
    encode(gen_random_bytes(16), 'hex'),
    'AlertBroadcast', 'SYSTEM', '通知', '緊急廣播',
    '全頁強制彈窗，用戶必須確認已讀才能關閉',
    '/static/modules/form_workflow/icons/workflow/alertbroadcast.svg',
    '{"broadcast_code": "string", "title": "string", "message": "string", "target_type": "string", "target_roles": "array", "target_departments": "array", "require_ack": "boolean"}',
    'modules.form_workflow.services.node_handlers.alert_broadcast_handler.AlertBroadcastHandler',
    false,
    'roundrectangle', '#3B82F6', 120, 60,
    -1, -1, 120, 3600,
    true, false, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM workflow_node_definitions WHERE node_type = 'AlertBroadcast');
