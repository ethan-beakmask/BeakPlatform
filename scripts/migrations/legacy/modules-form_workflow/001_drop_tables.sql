-- FormWorkflow Module - 資料表刪除腳本（回滾用）
-- 版本: 001
-- 說明: 刪除 form_workflow 模組的所有資料表
-- 執行方式: psql -U beakplatform -d beakplatform_dev -f 001_drop_tables.sql

-- 警告：此操作會刪除所有資料！

-- 刪除資料表（依相依性順序）
DROP TABLE IF EXISTS fw_workflow_variables CASCADE;
DROP TABLE IF EXISTS fw_node_execution_queue CASCADE;
DROP TABLE IF EXISTS fw_approval_records CASCADE;
DROP TABLE IF EXISTS fw_workflow_instances CASCADE;
DROP TABLE IF EXISTS fw_form_instances CASCADE;
DROP TABLE IF EXISTS fw_workflow_templates CASCADE;
DROP TABLE IF EXISTS fw_form_templates CASCADE;

-- 完成訊息
DO $$
BEGIN
    RAISE NOTICE '======================================';
    RAISE NOTICE 'FormWorkflow 模組資料表已刪除';
    RAISE NOTICE '======================================';
END $$;
