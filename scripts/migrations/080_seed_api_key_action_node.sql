-- 080: 註冊 ApiKeyAction 節點到 workflow_node_definitions (P3)
-- 建立日期: 2026-07-08
-- 對應 handler: modules/form_workflow/services/node_handlers/api_key_action_handler.py
-- 規格: dev-notes/API_KEY_TRIGGER_SPEC.md
--
-- 暫停/復原平台 API Key 的機器處置節點。處置對象限本企業 key
-- (handler 以 org_secure_code 強制租戶隔離)，故不需 require_system_admin。

INSERT INTO workflow_node_definitions (
    secure_code,
    node_type,
    scope,
    org_secure_code,
    category,
    display_name,
    description,
    icon,
    execution_handler,
    config_schema,
    canvas_shape,
    canvas_color,
    canvas_width,
    canvas_height,
    max_input_connections,
    max_output_connections,
    default_timeout_seconds,
    max_timeout_seconds,
    require_system_admin,
    is_active,
    is_deleted,
    created_at,
    updated_at
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    'ApiKeyAction',
    'SYSTEM',
    NULL,
    '安全',
    'API Key 處置',
    '暫停或復原平台 API Key（機器處置疑似盜用）。可處置發動本流程的 Key、指定 Key，或由變數解析 key_id。暫停原因支援變數，如 ${fi.serial}。',
    '/static/modules/form_workflow/icons/workflow/apikeyaction.svg',
    'modules.form_workflow.services.node_handlers.api_key_action_handler.ApiKeyActionHandler',
    '{
        "action": "string",
        "key_source": "string",
        "key_id": "string",
        "reason": "string"
    }'::jsonb,
    'roundrectangle',
    '#DC2626',
    140,
    60,
    -1,
    -1,
    60,
    600,
    FALSE,
    TRUE,
    FALSE,
    NOW(),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM workflow_node_definitions WHERE node_type = 'ApiKeyAction'
);
