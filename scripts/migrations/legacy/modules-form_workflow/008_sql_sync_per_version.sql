-- 008: SQL 同步從配對層級移至發行版本層級
-- 每個發行版本獨立控制是否啟用 SQL 同步

-- 1. 在 fw_published_form_workflows 加入 sql_sync_enabled 欄位
ALTER TABLE fw_published_form_workflows
    ADD COLUMN IF NOT EXISTS sql_sync_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. 遷移既有資料：有 registry 的版本標記為已啟用
UPDATE fw_published_form_workflows pfw
SET sql_sync_enabled = TRUE
WHERE EXISTS (
    SELECT 1 FROM fw_sql_form_registries r
    WHERE r.published_secure_code = pfw.secure_code
);

-- 3. 遷移既有資料：mapping 層級已啟用但尚未建立 registry 的版本也標記
UPDATE fw_published_form_workflows pfw
SET sql_sync_enabled = TRUE
FROM fw_form_workflow_mappings fwm
WHERE pfw.source_mapping_secure_code = fwm.secure_code
  AND fwm.sql_sync_enabled = TRUE
  AND pfw.sql_sync_enabled = FALSE;

-- 注意：fw_form_workflow_mappings.sql_sync_enabled 欄位保留但不再使用
-- 後續可考慮移除
