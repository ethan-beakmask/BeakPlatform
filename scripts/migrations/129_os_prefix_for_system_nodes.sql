-- 129_os_prefix_for_system_nodes.sql
--
-- 系統級節點加 OS 前綴識別（Ethan 2026-08-31 裁示）：
--   FileRead  -> OsFileRead     檔案讀取 -> OS 檔案讀取
--   FileWrite -> OsFileWrite    檔案寫入 -> OS 檔案寫入
--   OsExecutor 已有前綴，不動
--
-- 判準是「碰觸作業系統」而不是「系統管理員專用」，所以 SysTelegram 不在此列
-- （它已有 Sys 前綴，且不碰 OS）。
--
-- 為什麼要一併改 graph / queue / logs：node_type 是 factory 查 handler 的鍵，
-- 已存在流程圖裡的舊字串若不換，該流程執行時 NodeHandlerFactory.create() 會拋
-- ValueError（前例：ParallelFork 退役時 handler 註冊刻意保留，就是因為 16 筆
-- 發行快照裡還留著它）。本次執行時發行快照為 0 筆，是改名成本最低的時機。
--
-- 系統設定鍵一併改前綴，避免「OsFileWrite 節點讀 file_write_base_dirs」的錯位。
-- .env 的開關同步改名為 OS_FILE_READ_NODE_ENABLED / OS_FILE_WRITE_NODE_ENABLED，
-- 那不在 DB，部署時要手動改（見 docs/install/os_node.md 與 os_file_write_node.md）。
--
-- 冪等：以舊名為條件，重跑時 0 筆。
BEGIN;

-- 1. 節點定義（node_type / display_name / icon / execution_handler）
UPDATE workflow_node_definitions
SET node_type = 'OsFileRead',
    display_name = 'OS 檔案讀取',
    icon = '/static/modules/form_workflow/icons/workflow/osfileread.svg',
    execution_handler = 'modules.form_workflow.services.node_handlers.os_file_read_handler.OsFileReadHandler',
    updated_at = NOW()
WHERE node_type = 'FileRead';

UPDATE workflow_node_definitions
SET node_type = 'OsFileWrite',
    display_name = 'OS 檔案寫入',
    icon = '/static/modules/form_workflow/icons/workflow/osfilewrite.svg',
    execution_handler = 'modules.form_workflow.services.node_handlers.os_file_write_handler.OsFileWriteHandler',
    updated_at = NOW()
WHERE node_type = 'FileWrite';

-- 2. 企業授權（含已軟刪除的歷史列，讓授權歷史仍可追）
UPDATE workflow_node_org_grants SET node_type = 'OsFileRead'  WHERE node_type = 'FileRead';
UPDATE workflow_node_org_grants SET node_type = 'OsFileWrite' WHERE node_type = 'FileWrite';

-- 3. 流程圖：引擎讀 graph、設計器讀 cytoscape_config，兩欄都要換
UPDATE fw_workflow_templates
SET graph = replace(replace(graph::text, '"FileRead"', '"OsFileRead"'),
                    '"FileWrite"', '"OsFileWrite"')::jsonb,
    updated_at = NOW()
WHERE graph::text LIKE '%"FileRead"%' OR graph::text LIKE '%"FileWrite"%';

UPDATE fw_workflow_templates
SET cytoscape_config = replace(replace(cytoscape_config::text, '"FileRead"', '"OsFileRead"'),
                               '"FileWrite"', '"OsFileWrite"')::jsonb,
    updated_at = NOW()
WHERE cytoscape_config::text LIKE '%"FileRead"%' OR cytoscape_config::text LIKE '%"FileWrite"%';

-- 4. 發行快照（本次執行時為 0 筆，仍寫進來以防日後重跑於其他環境）
UPDATE fw_published_form_workflows
SET workflow_snapshot = replace(replace(workflow_snapshot::text, '"FileRead"', '"OsFileRead"'),
                                '"FileWrite"', '"OsFileWrite"')::json
WHERE workflow_snapshot::text LIKE '%"FileRead"%' OR workflow_snapshot::text LIKE '%"FileWrite"%';

-- 5. 執行紀錄（歷史資料，換名以免同一個節點在紀錄裡有兩種稱呼）
UPDATE fw_node_execution_queue SET node_type = 'OsFileRead'  WHERE node_type = 'FileRead';
UPDATE fw_node_execution_queue SET node_type = 'OsFileWrite' WHERE node_type = 'FileWrite';
UPDATE fw_node_execution_logs  SET node_type = 'OsFileRead'  WHERE node_type = 'FileRead';
UPDATE fw_node_execution_logs  SET node_type = 'OsFileWrite' WHERE node_type = 'FileWrite';

-- 6. 系統設定鍵（目錄白名單）
UPDATE system_settings SET key = 'os_file_read_base_dirs'      WHERE key = 'file_read_base_dirs';
UPDATE system_settings SET key = 'os_file_read_org_base_dirs'  WHERE key = 'file_read_org_base_dirs';
UPDATE system_settings SET key = 'os_file_write_base_dirs'     WHERE key = 'file_write_base_dirs';
UPDATE system_settings SET key = 'os_file_write_org_base_dirs' WHERE key = 'file_write_org_base_dirs';

-- 7. 這幾筆設定的 category 標籤（設定頁分組用，純內部標籤）也帶前綴，
--    否則 key 是 os_file_write_base_dirs 而 category 是 file_write，看起來像兩個東西
UPDATE system_settings SET category = 'os_file_read'  WHERE category = 'file_read';
UPDATE system_settings SET category = 'os_file_write' WHERE category = 'file_write';

COMMIT;
