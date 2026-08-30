-- 120: 註冊 OsExecutor 節點到 workflow_node_definitions
-- 建立日期: 2026-08-30
-- 對應 handler: modules/form_workflow/services/node_handlers/os_executor_handler.py
--
-- is_active=FALSE 是刻意的：OsExecutor 等同平台主機 shell，預設必須 fail-closed。
-- 啟用步驟：
--   1. .env 設 OS_NODE_ENABLED=1 並重啟 executor
--   2. UPDATE workflow_node_definitions SET is_active=true WHERE node_type='OsExecutor';
--   3. 將允許企業 secure_code 寫入 system_settings.os_node_allowed_orgs

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
    'OsExecutor',
    'SYSTEM',
    NULL,
    '系統',
    'OS 命令',
    '在平台主機執行命令，需系統管理員在 .env 啟用並把企業加入 os_node_allowed_orgs 白名單。',
    '/static/modules/form_workflow/icons/workflow/osexecutor.svg',
    'modules.form_workflow.services.node_handlers.os_executor_handler.OsExecutorHandler',
    '{
        "command": "string",
        "timeout_seconds": "integer",
        "result_var": "string",
        "wait_for_result": "boolean",
        "expect_exit_codes": "array",
        "expect_pattern": "string",
        "expect_json": "boolean",
        "cwd": "string",
        "extra_env": "object",
        "kill_on_timeout": "string",
        "cancel_scope": "string",
        "stop_after": "boolean",
        "notify_on_exception": "boolean",
        "notify_to": "array"
    }'::jsonb,
    'roundrectangle',
    '#B45309',
    130,
    60,
    -1,
    -1,
    60,
    3600,
    FALSE,
    FALSE,
    FALSE,
    NOW(),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM workflow_node_definitions WHERE node_type = 'OsExecutor'
);

INSERT INTO system_settings (
    secure_code,
    key,
    value,
    value_type,
    description,
    category,
    updated_by,
    created_at,
    updated_at,
    is_deleted
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    'os_node_allowed_orgs',
    '[]',
    'json',
    '允許執行 OsExecutor 節點的企業 secure_code 清單；預設空清單表示全部拒絕。',
    'os_node',
    'SYSTEM',
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'os_node_allowed_orgs'
);
