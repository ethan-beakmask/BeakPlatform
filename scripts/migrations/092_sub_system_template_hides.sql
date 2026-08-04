-- 092: Sub-system page template hides
-- 日期: 2026-08-04
-- 用途: 讓 NoCode 子系統可隱藏平台內建頁面樣板但不刪除樣板本身。

BEGIN;

CREATE TABLE IF NOT EXISTS dc_sub_system_template_hides (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    sub_system_secure_code VARCHAR(32) NOT NULL,
    template_secure_code VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    deleted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dc_sub_system_template_hides_org_secure_code
  ON dc_sub_system_template_hides(org_secure_code);

CREATE INDEX IF NOT EXISTS idx_dc_sub_system_template_hides_sub_system_secure_code
  ON dc_sub_system_template_hides(sub_system_secure_code);

CREATE INDEX IF NOT EXISTS idx_dc_sub_system_template_hides_template_secure_code
  ON dc_sub_system_template_hides(template_secure_code);

ALTER TABLE dc_sub_system_template_hides
  DROP CONSTRAINT IF EXISTS uq_dc_sub_system_template_hides;

ALTER TABLE dc_sub_system_template_hides
  ADD CONSTRAINT uq_dc_sub_system_template_hides
  UNIQUE (sub_system_secure_code, template_secure_code);

COMMIT;
