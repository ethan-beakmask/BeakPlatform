-- 037: 清除舊平台層表單/流程表
-- 這些表已被 fw_ 前綴的模組層表完全取代
-- ORM 不再引用，最後寫入時間: 2026-01-23
-- 備份: beakplatform_dev_20260308
-- CASCADE 僅移除舊表之間的 FK constraint，不影響其他表

BEGIN;

DROP TABLE IF EXISTS form_approval_comments CASCADE;
DROP TABLE IF EXISTS node_execution_logs CASCADE;
DROP TABLE IF EXISTS node_execution_queue CASCADE;
DROP TABLE IF EXISTS node_execution_queue_archive CASCADE;
DROP TABLE IF EXISTS workflow_variables CASCADE;
DROP TABLE IF EXISTS form_instances CASCADE;
DROP TABLE IF EXISTS workflow_instances CASCADE;
DROP TABLE IF EXISTS published_form_workflows CASCADE;
DROP TABLE IF EXISTS form_workflow_mappings CASCADE;
DROP TABLE IF EXISTS form_categories CASCADE;
DROP TABLE IF EXISTS form_templates CASCADE;
DROP TABLE IF EXISTS workflow_templates CASCADE;

COMMIT;
