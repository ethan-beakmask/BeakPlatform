-- FormWorkflow Module - 回滾腳本
-- 版本: 003
-- 說明: 刪除表單流程配對相關資料表
-- 執行方式: psql -U beakplatform -d beakplatform_dev -f 003_drop_mapping_tables.sql

-- 刪除已發行表單流程配對表
DROP TABLE IF EXISTS fw_published_form_workflows CASCADE;

-- 刪除表單-流程配對表
DROP TABLE IF EXISTS fw_form_workflow_mappings CASCADE;

DO $$
BEGIN
    RAISE NOTICE '======================================';
    RAISE NOTICE 'FormWorkflow 配對資料表已刪除';
    RAISE NOTICE '======================================';
END $$;
