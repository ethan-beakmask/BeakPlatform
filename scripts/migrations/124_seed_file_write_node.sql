-- 124: 註冊 FileWrite 節點到 workflow_node_definitions
-- 建立日期: 2026-08-31
-- 對應 handler: modules/form_workflow/services/node_handlers/file_write_handler.py
--
-- is_active=FALSE 是刻意的：FileWrite 會對平台主機檔案追加內容，
-- 預設必須 fail-closed。
-- 啟用步驟：
--   1. .env 設 FILE_WRITE_NODE_ENABLED=1 並重啟 executor
--   2. UPDATE workflow_node_definitions SET is_active=true WHERE node_type='FileWrite';
--   3. 在 workflow_node_org_grants 授權允許企業使用 FileWrite
--   4. 設定 system_settings.file_write_base_dirs 與 file_write_org_base_dirs

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
    org_restricted,
    is_active,
    is_deleted,
    created_at,
    updated_at
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    'FileWrite',
    'SYSTEM',
    NULL,
    '系統',
    '檔案寫入',
    '對允許目錄下的檔案追加字串；會先清掉檔尾既有換行再依勾選補換行。需在 .env 啟用並授權企業。',
    '/static/modules/form_workflow/icons/workflow/filewrite.svg',
    'modules.form_workflow.services.node_handlers.file_write_handler.FileWriteHandler',
    '{
        "base_dir": "string",
        "file_path": "string",
        "content": "string",
        "newline_before": "boolean",
        "newline_after": "boolean",
        "create_if_missing": "boolean",
        "encoding": "string",
        "max_file_bytes": "integer",
        "lock_timeout_ms": "integer",
        "result_var": "string",
        "stop_after": "boolean"
    }'::jsonb,
    'roundrectangle',
    '#B45309',
    130,
    60,
    -1,
    -1,
    60,
    600,
    FALSE,
    TRUE,
    FALSE,
    FALSE,
    NOW(),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM workflow_node_definitions WHERE node_type = 'FileWrite'
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
    'file_write_base_dirs',
    '[]',
    'json',
    'FileWrite 全平台可寫 base_dir 上限；預設空清單表示全部拒絕。',
    'file_write',
    'SYSTEM',
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'file_write_base_dirs'
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
    'file_write_org_base_dirs',
    '{}',
    'json',
    '各企業 FileWrite 可寫 base_dir 子集，key 為 org secure_code；企業無設定時不再收窄平台清單。',
    'file_write',
    'SYSTEM',
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE key = 'file_write_org_base_dirs'
);

INSERT INTO workflow_node_org_grants (
    secure_code, node_type, org_secure_code, granted_by_secure_code,
    granted_by_name, note, created_at, updated_at, is_deleted
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    'FileWrite', organizations.secure_code, NULL,
    'migration_124', 'system_org_default', NOW(), NOW(), FALSE
FROM organizations
WHERE organizations.is_system_org = TRUE
  AND organizations.is_deleted = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM workflow_node_org_grants existing
       WHERE existing.node_type = 'FileWrite'
         AND existing.org_secure_code = organizations.secure_code
         AND existing.is_deleted = FALSE
  );
