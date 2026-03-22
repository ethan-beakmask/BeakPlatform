-- 048: 建立 broadcast_acknowledgments 表
-- 用於 AlertBroadcast 節點的已讀確認追蹤

CREATE TABLE IF NOT EXISTS broadcast_acknowledgments (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    broadcast_secure_code VARCHAR(32) NOT NULL,
    user_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code),
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),
    acknowledged_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_broadcast_ack_broadcast ON broadcast_acknowledgments(broadcast_secure_code);
CREATE INDEX IF NOT EXISTS ix_broadcast_ack_user ON broadcast_acknowledgments(user_secure_code);
CREATE INDEX IF NOT EXISTS ix_broadcast_ack_org ON broadcast_acknowledgments(org_secure_code);
CREATE UNIQUE INDEX IF NOT EXISTS ix_broadcast_ack_unique ON broadcast_acknowledgments(broadcast_secure_code, user_secure_code);
