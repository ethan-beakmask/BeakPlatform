-- 093: NoCode shared menus
-- 日期: 2026-08-04
-- 用途: 讓 NoCode 子系統可定義具名共用選單，Page IR menu widget 以引用方式共用 items。

BEGIN;

CREATE TABLE IF NOT EXISTS dc_shared_menus (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    sub_system_secure_code VARCHAR(32) NOT NULL,
    name VARCHAR(200) NOT NULL,
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    deleted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dc_shared_menus_org_secure_code
  ON dc_shared_menus(org_secure_code);

CREATE INDEX IF NOT EXISTS idx_dc_shared_menus_sub_system_secure_code
  ON dc_shared_menus(sub_system_secure_code);

CREATE INDEX IF NOT EXISTS idx_dc_shared_menus_is_active
  ON dc_shared_menus(is_active);

CREATE INDEX IF NOT EXISTS idx_dc_shared_menus_is_deleted
  ON dc_shared_menus(is_deleted);

CREATE INDEX IF NOT EXISTS idx_dc_shared_menus_sub_system_name_active
  ON dc_shared_menus(sub_system_secure_code, name)
  WHERE is_deleted = false;

COMMIT;
