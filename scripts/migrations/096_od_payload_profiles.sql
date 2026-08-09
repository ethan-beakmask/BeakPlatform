-- 096: OpenDefense 原生 payload 來源格式設定檔
-- 建立日期: 2026-08-10
-- 對應程式: modules/open_defense/models/payload_profile.py
--           modules/open_defense/services/payload_profile_service.py
--           modules/open_defense/api/intake_native.py
--           modules/open_defense/api/admin/payload_profiles.py
--
-- 新增 od_payload_profiles,支援 /api/open_defense/intake/native 依 profile
-- 將非 OCSF SOC 通報扁平化進 form_data,並以 payload_kind 區分路由規則。

CREATE TABLE IF NOT EXISTS od_payload_profiles (
    id                          SERIAL       PRIMARY KEY,
    secure_code                 VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code             VARCHAR(32)  NOT NULL,

    code                        VARCHAR(50)  NOT NULL,
    name                        VARCHAR(100) NOT NULL,
    source_system               VARCHAR(50)  NOT NULL,
    correlation_id_path         VARCHAR(200) NOT NULL,
    field_map                   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    severity_map                JSONB        NULL,
    detail_path                 VARCHAR(200) NULL,
    detail_item_key             VARCHAR(100) NULL,
    detail_columns              JSONB        NULL,
    subject_detail_key          VARCHAR(100) NULL,
    kv_expansions               JSONB        NULL,
    is_active                   BOOLEAN      NOT NULL DEFAULT TRUE,
    note                        VARCHAR(500) NULL,

    created_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted                  BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at                  TIMESTAMP    NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_od_payload_profiles_org_code_active
    ON od_payload_profiles(org_secure_code, code)
    WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS idx_od_payload_profiles_org
    ON od_payload_profiles(org_secure_code);

ALTER TABLE od_payload_profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_od_payload_profiles_tenant ON od_payload_profiles;
CREATE POLICY p_od_payload_profiles_tenant ON od_payload_profiles
    USING (org_secure_code = current_setting('app.current_org', true));

-- 既有安裝補欄位(本檔在 2026-08-10 當日補加 subject_detail_key)
ALTER TABLE od_payload_profiles
    ADD COLUMN IF NOT EXISTS subject_detail_key VARCHAR(100);

ALTER TABLE od_form_template_mappings
    ADD COLUMN IF NOT EXISTS payload_kind VARCHAR(10);

COMMENT ON TABLE od_payload_profiles IS
  'OpenDefense: 原生 SOC payload 來源格式設定檔';

COMMENT ON TABLE od_form_template_mappings IS
  'OpenDefense: 規則式事件路由,依 event_class/payload_kind/條件/priority 決定 form_template';
