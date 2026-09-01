-- FormWorkflow Module - Migration 002
-- 新增子流程相關欄位
-- 執行時間: 執行前請確認 001 已完成

-- 1. fw_workflow_instances 新增子流程欄位
ALTER TABLE fw_workflow_instances
    ADD COLUMN IF NOT EXISTS parent_instance_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS root_instance_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS workflow_depth INTEGER DEFAULT 0 NOT NULL;

-- 2. fw_node_execution_queue 新增子流程和表單關聯欄位
ALTER TABLE fw_node_execution_queue
    ADD COLUMN IF NOT EXISTS form_instance_secure_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS calling_instance_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS parent_node_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 5 NOT NULL;

-- 3. 建立索引
CREATE INDEX IF NOT EXISTS idx_fw_workflow_instances_parent ON fw_workflow_instances(parent_instance_code);
CREATE INDEX IF NOT EXISTS idx_fw_workflow_instances_root ON fw_workflow_instances(root_instance_code);
CREATE INDEX IF NOT EXISTS idx_fw_node_queue_form ON fw_node_execution_queue(form_instance_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_node_queue_calling ON fw_node_execution_queue(calling_instance_code);

-- 驗證
SELECT 'Migration 002 completed - SubFlow columns added' AS status;
