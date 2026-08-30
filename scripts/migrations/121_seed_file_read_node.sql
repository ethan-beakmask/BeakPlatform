-- 121: 註冊 FileRead 節點到 workflow_node_definitions
-- 建立日期: 2026-08-30
-- 對應 handler: modules/form_workflow/services/node_handlers/file_read_handler.py
--
-- is_active=FALSE 是刻意的：FileRead 雖然唯讀且不經 shell，仍可讀平台主機檔案，
-- 預設必須 fail-closed。
-- 啟用步驟：
--   1. .env 設 FILE_READ_NODE_ENABLED=1 並重啟 executor
--   2. UPDATE workflow_node_definitions SET is_active=true WHERE node_type='FileRead';
--   3. 將允許企業 secure_code 寫入 system_settings.file_read_allowed_orgs
--   4. 設定 system_settings.file_read_base_dirs 與 file_read_org_base_dirs
--
-- /opt/tmp/osnode/ 不會自動加入 file_read_base_dirs；若要讓 FileRead 讀取
-- OsExecutor 的輸出全文，部署時必須明確把該目錄加入允許清單。

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
    'FileRead',
    'SYSTEM',
    NULL,
    '系統',
    '檔案讀取',
    '唯讀、不經 shell、鎖在允許目錄內；需在 .env 啟用並設定企業白名單與允許目錄。',
    '/static/modules/form_workflow/icons/workflow/fileread.svg',
    'modules.form_workflow.services.node_handlers.file_read_handler.FileReadHandler',
    '{
        "base_dir": "string",
        "file_path": "string",
        "result_var": "string",
        "mode": "string",
        "lines": "integer",
        "keyword": "string",
        "before": "integer",
        "after": "integer",
        "occurrence": "string",
        "max_windows": "integer",
        "match_scope": "string",
        "match_mode": "string",
        "max_scan_bytes": "integer",
        "max_scan_ms": "integer",
        "encoding": "string",
        "stop_after": "boolean"
    }'::jsonb,
    'roundrectangle',
    '#0F766E',
    130,
    60,
    -1,
    -1,
    60,
    600,
    FALSE,
    FALSE,
    FALSE,
    NOW(),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM workflow_node_definitions WHERE node_type = 'FileRead'
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
    'file_read_allowed_orgs',
    '[]',
    'json',
    '允許執行 FileRead 節點的企業 secure_code 清單；預設空清單表示全部拒絕。',
    'file_read',
    'SYSTEM',
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'file_read_allowed_orgs'
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
    'file_read_base_dirs',
    '[]',
    'json',
    'FileRead 全平台可讀 base_dir 上限；預設空清單表示全部拒絕。',
    'file_read',
    'SYSTEM',
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'file_read_base_dirs'
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
    'file_read_org_base_dirs',
    '{}',
    'json',
    '各企業 FileRead 可讀 base_dir 子集，key 為 org secure_code；企業無設定時不再收窄平台清單。',
    'file_read',
    'SYSTEM',
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'file_read_org_base_dirs'
);
