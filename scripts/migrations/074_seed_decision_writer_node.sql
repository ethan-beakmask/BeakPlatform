-- 074: 註冊 DecisionWriter 節點到 workflow_node_definitions
-- 建立日期: 2026-05-09
-- 對應 handler: modules/form_workflow/services/node_handlers/decision_writer_handler.py
--
-- 此節點寫入 od_defense_decisions 一筆,屬高敏感操作(對外執行端會直接拉去阻擋),
-- 透過 require_system_admin=true 限制只有系統管理員能在 workflow-designer 放置。
-- 後續若導入 'open_defense.decision.write' 角色守衛,可改 require_system_admin=false 並由
-- 角色守衛接管。

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
    'DecisionWriter',
    'SYSTEM',
    NULL,
    '安全',
    '防禦決策',
    '寫入一筆 OpenDefense 防禦決策(廠牌中性);任何外部執行端依 enforcement_points 篩選後拉取執行。target_value 通常引用表單欄位,如 ${f.actor_ip}。',
    '/static/modules/form_workflow/icons/workflow/decisionwriter.svg',
    'modules.form_workflow.services.node_handlers.decision_writer_handler.DecisionWriterHandler',
    '{
        "action": "string",
        "target_type": "string",
        "target_value": "string",
        "enforcement_points": "array",
        "severity": "string",
        "ttl_seconds": "integer",
        "reason_template": "string",
        "decided_via": "string"
    }'::jsonb,
    'roundrectangle',
    '#DC2626',
    140,
    60,
    -1,
    -1,
    60,
    600,
    TRUE,
    TRUE,
    FALSE,
    NOW(),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM workflow_node_definitions WHERE node_type = 'DecisionWriter'
);
