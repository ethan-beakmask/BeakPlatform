-- 088: NoCode portal form submit foundation
-- 日期: 2026-07-29
-- 用途: 讓 NoCode portal 表單送件可追蹤公用帳號與 portal 使用者識別。

BEGIN;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS is_service_account BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE fw_workflow_instances
  ADD COLUMN IF NOT EXISTS nocode_sub_system_sc VARCHAR(32),
  ADD COLUMN IF NOT EXISTS nocode_user_ref      VARCHAR(64);

CREATE INDEX IF NOT EXISTS ix_fw_wi_nocode
  ON fw_workflow_instances (nocode_sub_system_sc, nocode_user_ref);

COMMIT;
