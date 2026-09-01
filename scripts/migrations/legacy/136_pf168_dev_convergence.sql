-- 136_pf168_dev_convergence.sql
-- PF-168: dev 庫一次性收斂到「ORM model 為權威」的 schema。
-- 2026-09-01 對 beakplatform_dev 執行完畢後隨整批 migration 歸檔至 legacy/。
-- 全新安裝走 db.create_all()，不需要也不應該跑本檔。
--
-- 對照依據: scripts/schema_drift_diff.py 的比對輸出
-- (/opt/tmp/verify/20260901-pf168-drift-baseline.log)

BEGIN;

-- 一、死欄位（唯一使用者 WorkflowEngine.start_workflow / start_pure_workflow /
--     get_pending_tasks 為零呼叫者死碼，已於同日刪除；title 900 列全 NULL）
ALTER TABLE fw_form_instances DROP COLUMN IF EXISTS title;
ALTER TABLE fw_published_form_workflows DROP COLUMN IF EXISTS numbering_rule_secure_code;
ALTER TABLE fw_workflow_instances DROP COLUMN IF EXISTS created_by_secure_code;
ALTER TABLE fw_workflow_instances DROP COLUMN IF EXISTS timeout_at;
ALTER TABLE fw_workflow_templates DROP COLUMN IF EXISTS timeout_minutes;

-- 二、model 有、dev 沒有的欄位
ALTER TABLE dc_bridge_logs ADD COLUMN IF NOT EXISTS updated_at timestamp;
UPDATE dc_bridge_logs SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE dc_bridge_logs ALTER COLUMN updated_at SET NOT NULL;

-- 三、timestamptz -> timestamp（TZ-01：DB 一律存 naive UTC；錯的是 dev 這邊）
ALTER TABLE fw_categories
  ALTER COLUMN created_at TYPE timestamp USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN updated_at TYPE timestamp USING updated_at AT TIME ZONE 'UTC',
  ALTER COLUMN deleted_at TYPE timestamp USING deleted_at AT TIME ZONE 'UTC';
ALTER TABLE fw_workflow_backgrounds
  ALTER COLUMN created_at TYPE timestamp USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN updated_at TYPE timestamp USING updated_at AT TIME ZONE 'UTC',
  ALTER COLUMN deleted_at TYPE timestamp USING deleted_at AT TIME ZONE 'UTC';
ALTER TABLE user_unit_memberships
  ALTER COLUMN created_at TYPE timestamp USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN updated_at TYPE timestamp USING updated_at AT TIME ZONE 'UTC',
  ALTER COLUMN deleted_at TYPE timestamp USING deleted_at AT TIME ZONE 'UTC';
ALTER TABLE password_reset_tokens
  ALTER COLUMN created_at TYPE timestamp USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN updated_at TYPE timestamp USING updated_at AT TIME ZONE 'UTC',
  ALTER COLUMN deleted_at TYPE timestamp USING deleted_at AT TIME ZONE 'UTC',
  ALTER COLUMN expires_at TYPE timestamp USING expires_at AT TIME ZONE 'UTC',
  ALTER COLUMN used_at TYPE timestamp USING used_at AT TIME ZONE 'UTC',
  ALTER COLUMN verified_at TYPE timestamp USING verified_at AT TIME ZONE 'UTC';

-- 四、補 NOT NULL（執行當下已確認全部 0 NULL，backfill 為保險）
UPDATE audit_logs SET updated_at = COALESCE(created_at, now() AT TIME ZONE 'UTC') WHERE updated_at IS NULL;
ALTER TABLE audit_logs ALTER COLUMN updated_at SET NOT NULL;

UPDATE conglomerate_logs SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE conglomerate_logs SET updated_at = created_at WHERE updated_at IS NULL;
UPDATE conglomerate_logs SET is_deleted = false WHERE is_deleted IS NULL;
ALTER TABLE conglomerate_logs
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL;

UPDATE dc_backgrounds SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE dc_backgrounds SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE dc_backgrounds
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL;

UPDATE dc_permission_policy_groups SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE dc_permission_policy_groups SET updated_at = created_at WHERE updated_at IS NULL;
UPDATE dc_permission_policy_groups SET is_deleted = false WHERE is_deleted IS NULL;
ALTER TABLE dc_permission_policy_groups
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL;

UPDATE dc_permission_policy_rules SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE dc_permission_policy_rules SET updated_at = created_at WHERE updated_at IS NULL;
UPDATE dc_permission_policy_rules SET is_deleted = false WHERE is_deleted IS NULL;
UPDATE dc_permission_policy_rules SET include_children = false WHERE include_children IS NULL;
ALTER TABLE dc_permission_policy_rules
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL,
  ALTER COLUMN include_children SET NOT NULL;

UPDATE fw_categories SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE fw_categories SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE fw_categories
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL;

UPDATE fw_form_field_changes SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE fw_form_field_changes SET updated_at = created_at WHERE updated_at IS NULL;
UPDATE fw_form_field_changes SET is_deleted = false WHERE is_deleted IS NULL;
ALTER TABLE fw_form_field_changes
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL;

UPDATE fw_mapping_permissions SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE fw_mapping_permissions SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE fw_mapping_permissions
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL;

UPDATE fw_sql_form_registries SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE fw_sql_form_registries SET updated_at = created_at WHERE updated_at IS NULL;
UPDATE fw_sql_form_registries SET is_deleted = false WHERE is_deleted IS NULL;
ALTER TABLE fw_sql_form_registries
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL;

UPDATE fw_workflow_backgrounds SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE fw_workflow_backgrounds SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE fw_workflow_backgrounds
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE password_history
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN secure_code SET NOT NULL;

UPDATE password_reset_tokens SET is_deleted = false WHERE is_deleted IS NULL;
ALTER TABLE password_reset_tokens
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL;

ALTER TABLE personal_schedules
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL,
  ALTER COLUMN source SET NOT NULL;

ALTER TABLE schedule_adjustments
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL,
  ALTER COLUMN status SET NOT NULL;

ALTER TABLE schedule_holidays
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL;

ALTER TABLE shift_types
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL,
  ALTER COLUMN is_active SET NOT NULL,
  ALTER COLUMN sort_order SET NOT NULL;

UPDATE store_items SET updated_at = COALESCE(created_at, now() AT TIME ZONE 'UTC') WHERE updated_at IS NULL;
ALTER TABLE store_items ALTER COLUMN updated_at SET NOT NULL;

UPDATE user_unit_memberships SET is_deleted = false WHERE is_deleted IS NULL;
UPDATE user_unit_memberships SET created_at = now() AT TIME ZONE 'UTC' WHERE created_at IS NULL;
UPDATE user_unit_memberships SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE user_unit_memberships
  ALTER COLUMN is_deleted SET NOT NULL,
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL;

UPDATE users SET failed_login_count = 0 WHERE failed_login_count IS NULL;
ALTER TABLE users ALTER COLUMN failed_login_count SET NOT NULL;

ALTER TABLE work_schedules
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET NOT NULL,
  ALTER COLUMN is_deleted SET NOT NULL,
  ALTER COLUMN is_active SET NOT NULL,
  ALTER COLUMN is_default SET NOT NULL;

-- 五、放寬 NOT NULL（model 定義為 nullable，程式端 default=dict 一律有值）
ALTER TABLE dc_page_layouts ALTER COLUMN style_config DROP NOT NULL;
ALTER TABLE dc_sub_systems ALTER COLUMN bridge_rules DROP NOT NULL;
ALTER TABLE dc_sub_systems ALTER COLUMN style_config DROP NOT NULL;

-- 六、schema_migrations 退役（登記早已失真，migration 制度由 PF-168 廢止，
--     model 即權威；歷史封存在 scripts/migrations/legacy/）
DROP TABLE IF EXISTS schema_migrations;

COMMIT;
