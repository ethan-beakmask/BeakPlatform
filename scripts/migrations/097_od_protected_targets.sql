-- 097: OpenDefense 封鎖保護清單
-- 建立日期: 2026-08-13
-- 對應程式: modules/open_defense/models/protected_target.py
--           modules/open_defense/services/protected_target_service.py
--
-- PF-83: 於 decision_service.create_decision() 唯一寫入點加入服務層防護,
-- 避免反向代理、私有網段與其他受保護目標被誤寫成封鎖決策。

CREATE TABLE IF NOT EXISTS od_protected_targets (
    id                          SERIAL       PRIMARY KEY,
    secure_code                 VARCHAR(32)  UNIQUE NOT NULL,
    org_secure_code             VARCHAR(32)  NOT NULL,

    entry_type                  VARCHAR(10)  NOT NULL DEFAULT 'protect',
    target_value                VARCHAR(64)  NOT NULL,
    name                        VARCHAR(100) NULL,
    is_active                   BOOLEAN      NOT NULL DEFAULT TRUE,
    note                        VARCHAR(500) NULL,
    created_by_secure_code      VARCHAR(32)  NULL,

    created_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    is_deleted                  BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at                  TIMESTAMP    NULL
);

CREATE INDEX IF NOT EXISTS idx_od_protected_org_active
    ON od_protected_targets(org_secure_code, entry_type, is_active);

ALTER TABLE od_protected_targets ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_od_protected_targets_tenant ON od_protected_targets;
CREATE POLICY p_od_protected_targets_tenant ON od_protected_targets
    USING (org_secure_code = current_setting('app.current_org', true));

COMMENT ON TABLE od_protected_targets IS
  'OpenDefense: 封鎖保護清單,防止基礎設施與受保護目標被誤寫成封鎖決策';
