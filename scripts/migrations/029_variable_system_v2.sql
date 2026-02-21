-- Migration 029: Variable System v2
-- 變數系統改版：GLOBAL→FLOW, LOCAL→NODE, 新增 TREE scope + root_instance_code 欄位
-- 規格文件: docs/VARIABLE_SYSTEM_SPEC.md

BEGIN;

-- 1. 新增 root_instance_code 欄位（TREE scope 隔離鍵）
ALTER TABLE fw_workflow_variables
    ADD COLUMN IF NOT EXISTS root_instance_code VARCHAR(32);

-- 2. 建立 root_instance_code 索引
CREATE INDEX IF NOT EXISTS idx_fw_workflow_variables_root
    ON fw_workflow_variables (root_instance_code);

-- 3. 將既有 var_type 值遷移
UPDATE fw_workflow_variables SET var_type = 'FLOW' WHERE var_type = 'GLOBAL';
UPDATE fw_workflow_variables SET var_type = 'NODE' WHERE var_type = 'LOCAL';

-- 4. 為既有 FLOW 變數回填 root_instance_code（方便日後 TREE 查詢）
UPDATE fw_workflow_variables v
SET root_instance_code = wi.root_instance_code
FROM fw_workflow_instances wi
WHERE v.workflow_instance_secure_code = wi.secure_code
  AND v.root_instance_code IS NULL
  AND wi.root_instance_code IS NOT NULL;

-- 主流程的 root_instance_code 等於自身 secure_code
UPDATE fw_workflow_variables v
SET root_instance_code = wi.secure_code
FROM fw_workflow_instances wi
WHERE v.workflow_instance_secure_code = wi.secure_code
  AND v.root_instance_code IS NULL
  AND wi.root_instance_code IS NULL;

COMMIT;
