-- 130_sys_nodes_org_restricted.sql
--
-- 系統級通知節點改用企業授權機制（Ethan 2026-08-31 裁示）：
--   EmailRelay -> SysEmailRelay    Email 轉發 -> 系統 Email 轉發
--   SysTelegram 保持名稱，只切換授權欄位
--
-- 舊的 require_system_admin 只擋設計器可見性，不擋 graph 寫入 / publish / handler 執行。
-- 兩個系統級節點改用 org_restricted + workflow_node_org_grants，出廠只授權系統預設企業。
--
-- 為什麼要一併改 graph / queue / logs：node_type 是 factory 查 handler 的鍵，
-- 已存在流程圖裡的舊字串若不換，該流程執行時 NodeHandlerFactory.create() 會拋
-- ValueError。本次執行時既有流程用量為 0 筆，仍寫進來以防日後重跑於其他環境。
--
-- JSON 替換刻意使用帶引號的完整字面量，避免誤改 EmailRelayHandler 等子字串。
--
-- 冪等：以舊名或舊授權狀態為條件，重跑時 0 筆；授權插入用 NOT EXISTS 避免重複。
BEGIN;

-- 1. 節點定義（node_type / display_name / category / icon / execution_handler）
UPDATE workflow_node_definitions
SET node_type = 'SysEmailRelay',
    display_name = '系統 Email 轉發',
    category = '系統',
    icon = '/static/modules/form_workflow/icons/workflow/sysemailrelay.svg',
    execution_handler = 'modules.form_workflow.services.node_handlers.sys_emailrelay_handler.SysEmailRelayHandler',
    updated_at = NOW()
WHERE node_type = 'EmailRelay';

-- 2. 企業授權（含已軟刪除的歷史列，讓授權歷史仍可追）
UPDATE workflow_node_org_grants SET node_type = 'SysEmailRelay' WHERE node_type = 'EmailRelay';

-- 3. 流程圖：引擎讀 graph、設計器讀 cytoscape_config，兩欄都要換
UPDATE fw_workflow_templates
SET graph = replace(graph::text, '"EmailRelay"', '"SysEmailRelay"')::jsonb,
    updated_at = NOW()
WHERE graph::text LIKE '%"EmailRelay"%';

UPDATE fw_workflow_templates
SET cytoscape_config = replace(cytoscape_config::text, '"EmailRelay"', '"SysEmailRelay"')::jsonb,
    updated_at = NOW()
WHERE cytoscape_config::text LIKE '%"EmailRelay"%';

-- 4. 發行快照（本次執行時為 0 筆，仍寫進來以防日後重跑於其他環境）
UPDATE fw_published_form_workflows
SET workflow_snapshot = replace(workflow_snapshot::text, '"EmailRelay"', '"SysEmailRelay"')::json
WHERE workflow_snapshot::text LIKE '%"EmailRelay"%';

-- 5. 執行紀錄（歷史資料，換名以免同一個節點在紀錄裡有兩種稱呼）
UPDATE fw_node_execution_queue SET node_type = 'SysEmailRelay' WHERE node_type = 'EmailRelay';
UPDATE fw_node_execution_logs  SET node_type = 'SysEmailRelay' WHERE node_type = 'EmailRelay';

-- 6. 切換授權機制：舊欄位保留但不再使用
UPDATE workflow_node_definitions
SET org_restricted = TRUE,
    require_system_admin = FALSE,
    updated_at = NOW()
WHERE node_type IN ('SysTelegram', 'SysEmailRelay')
  AND (org_restricted IS DISTINCT FROM TRUE OR require_system_admin IS DISTINCT FROM FALSE);

-- 7. 出廠授權：系統預設企業可使用系統級通知節點
INSERT INTO workflow_node_org_grants (
    secure_code, node_type, org_secure_code, granted_by_secure_code,
    granted_by_name, note, created_at, updated_at, is_deleted
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    node_types.node_type, organizations.secure_code, NULL,
    'migration_130', 'system_org_default', NOW(), NOW(), FALSE
FROM organizations
CROSS JOIN (
    VALUES ('SysTelegram'), ('SysEmailRelay')
) AS node_types(node_type)
WHERE organizations.is_system_org = TRUE
  AND organizations.is_deleted = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM workflow_node_org_grants existing
       WHERE existing.node_type = node_types.node_type
         AND existing.org_secure_code = organizations.secure_code
         AND existing.is_deleted = FALSE
  );

COMMIT;
