-- 015: 建立簽核罐頭訊息表
-- 用途：儲存用戶的簽核意見快捷訊息

CREATE TABLE IF NOT EXISTS fw_approval_canned_messages (
    id              BIGSERIAL       PRIMARY KEY,
    secure_code     VARCHAR(32)     NOT NULL UNIQUE,
    org_secure_code VARCHAR(32)     NOT NULL,
    user_secure_code VARCHAR(32)    NOT NULL,
    text            TEXT            NOT NULL,
    sort_order      INTEGER         NOT NULL DEFAULT 0,
    is_deleted      BOOLEAN         NOT NULL DEFAULT FALSE,
    deleted_at      TIMESTAMP WITHOUT TIME ZONE,
    created_at      TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at      TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_fw_canned_msg_org ON fw_approval_canned_messages (org_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_canned_msg_user ON fw_approval_canned_messages (user_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_canned_msg_lookup ON fw_approval_canned_messages (org_secure_code, user_secure_code, is_deleted);
