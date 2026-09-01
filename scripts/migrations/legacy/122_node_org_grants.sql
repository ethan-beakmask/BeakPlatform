-- 122: 流程節點型別企業授權通用化
-- 建立 workflow_node_org_grants 授權表，並將 OsExecutor / FileRead 從舊 system_settings
-- 白名單遷移到通用授權機制。

ALTER TABLE workflow_node_definitions
    ADD COLUMN IF NOT EXISTS org_restricted BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS workflow_node_org_grants (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) UNIQUE NOT NULL,
    node_type VARCHAR(100) NOT NULL,
    org_secure_code VARCHAR(32) NOT NULL,
    granted_by_secure_code VARCHAR(32),
    granted_by_name VARCHAR(200),
    note TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workflow_node_org_grants_node_type
    ON workflow_node_org_grants (node_type);

CREATE INDEX IF NOT EXISTS idx_workflow_node_org_grants_org_secure_code
    ON workflow_node_org_grants (org_secure_code);

CREATE UNIQUE INDEX IF NOT EXISTS uq_node_org_grant_active
    ON workflow_node_org_grants (node_type, org_secure_code)
    WHERE is_deleted = false;

UPDATE workflow_node_definitions
   SET org_restricted = TRUE,
       updated_at = NOW()
 WHERE node_type IN ('OsExecutor', 'FileRead')
   AND is_deleted = FALSE;

INSERT INTO workflow_node_org_grants (
    secure_code,
    node_type,
    org_secure_code,
    granted_by_secure_code,
    granted_by_name,
    note,
    created_at,
    updated_at,
    is_deleted
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    migrated.node_type,
    migrated.org_secure_code,
    NULL,
    'migration_122',
    NULL,
    NOW(),
    NOW(),
    FALSE
FROM (
    SELECT 'OsExecutor' AS node_type, jsonb_array_elements_text(value::jsonb) AS org_secure_code
      FROM system_settings
     WHERE key = 'os_node_allowed_orgs'
       AND is_deleted = FALSE
       AND value IS NOT NULL
    UNION ALL
    SELECT 'FileRead' AS node_type, jsonb_array_elements_text(value::jsonb) AS org_secure_code
      FROM system_settings
     WHERE key = 'file_read_allowed_orgs'
       AND is_deleted = FALSE
       AND value IS NOT NULL
) AS migrated
WHERE migrated.org_secure_code <> ''
  AND NOT EXISTS (
      SELECT 1
        FROM workflow_node_org_grants existing
       WHERE existing.node_type = migrated.node_type
         AND existing.org_secure_code = migrated.org_secure_code
         AND existing.is_deleted = FALSE
  );

INSERT INTO workflow_node_org_grants (
    secure_code,
    node_type,
    org_secure_code,
    granted_by_secure_code,
    granted_by_name,
    note,
    created_at,
    updated_at,
    is_deleted
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    node_types.node_type,
    organizations.secure_code,
    NULL,
    'migration_122',
    'system_org_default',
    NOW(),
    NOW(),
    FALSE
FROM organizations
CROSS JOIN (
    SELECT 'OsExecutor' AS node_type
    UNION ALL
    SELECT 'FileRead' AS node_type
) AS node_types
WHERE organizations.is_system_org = TRUE
  AND organizations.is_deleted = FALSE
  AND NOT EXISTS (
      SELECT 1
        FROM workflow_node_org_grants existing
       WHERE existing.node_type = node_types.node_type
         AND existing.org_secure_code = organizations.secure_code
         AND existing.is_deleted = FALSE
  );

DELETE FROM system_settings
 WHERE key IN ('os_node_allowed_orgs', 'file_read_allowed_orgs');

-- 節點說明文字同步：120 / 121 寫入的說明提到已刪除的 system_settings 白名單，
-- 設計器面板會直接顯示這段文字，一併更新為新的授權機制。
UPDATE workflow_node_definitions
   SET description = '在平台主機執行命令，需系統管理員在 .env 啟用，並由主機管理員授權企業使用本節點。',
       updated_at = NOW()
 WHERE node_type = 'OsExecutor';

UPDATE workflow_node_definitions
   SET description = '唯讀、不經 shell、鎖在允許目錄內；需在 .env 啟用，並由主機管理員授權企業使用本節點與設定允許目錄。',
       updated_at = NOW()
 WHERE node_type = 'FileRead';

