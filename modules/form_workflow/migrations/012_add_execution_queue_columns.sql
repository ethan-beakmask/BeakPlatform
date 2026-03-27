-- 012: 補齊 fw_node_execution_queue 缺失欄位
-- Issue #20: migration 007 失敗導致 locked_by 欄位缺失
--
-- 補上 ORM model 已定義但 001_create_tables.sql 未包含的欄位:
--   - form_instance_secure_code (子流程關聯)
--   - calling_instance_code (子流程調用方)
--   - parent_node_id (子流程父節點)
--   - priority (執行優先序)
--   - locked_by (簽核鎖定者)
--   - locked_at (簽核鎖定時間)
--
-- 冪等: 所有操作都使用 IF NOT EXISTS / 條件判斷

BEGIN;

-- 表單實例關聯
ALTER TABLE fw_node_execution_queue
    ADD COLUMN IF NOT EXISTS form_instance_secure_code VARCHAR(32);

-- 子流程關聯
ALTER TABLE fw_node_execution_queue
    ADD COLUMN IF NOT EXISTS calling_instance_code VARCHAR(32);

ALTER TABLE fw_node_execution_queue
    ADD COLUMN IF NOT EXISTS parent_node_id VARCHAR(100);

-- 執行優先序
ALTER TABLE fw_node_execution_queue
    ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 5;

-- 簽核鎖定
ALTER TABLE fw_node_execution_queue
    ADD COLUMN IF NOT EXISTS locked_by VARCHAR(32);

ALTER TABLE fw_node_execution_queue
    ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP;

-- 補充 comment（僅 locked_by / locked_at）
COMMENT ON COLUMN fw_node_execution_queue.locked_by IS '鎖定者 user_secure_code';
COMMENT ON COLUMN fw_node_execution_queue.locked_at IS '鎖定時間 (UTC)';

-- 索引
CREATE INDEX IF NOT EXISTS idx_fw_node_queue_form
    ON fw_node_execution_queue(form_instance_secure_code);

CREATE INDEX IF NOT EXISTS idx_fw_node_queue_calling
    ON fw_node_execution_queue(calling_instance_code);

-- 活躍節點唯一約束（同一流程實例中，同一節點只能有一個活躍執行）
CREATE UNIQUE INDEX IF NOT EXISTS idx_fw_queue_active_node
    ON fw_node_execution_queue(workflow_instance_secure_code, node_id)
    WHERE status IN ('PENDING', 'RUNNING', 'WAITING');

COMMIT;
