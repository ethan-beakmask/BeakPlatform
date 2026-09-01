-- 集團操作日誌表
-- 記錄企業加入/退出集團的歷史

CREATE TABLE IF NOT EXISTS conglomerate_logs (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),

    -- 集團識別碼
    conglomerate_secure_code VARCHAR(32) NOT NULL REFERENCES conglomerates(secure_code),

    -- 企業識別碼
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 操作類型: JOIN, LEAVE
    action VARCHAR(20) NOT NULL,

    -- 操作者信箱
    operator_email VARCHAR(255) NOT NULL,

    -- 操作描述
    description TEXT,

    -- 時間戳記
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_conglomerate_logs_conglomerate ON conglomerate_logs(conglomerate_secure_code);
CREATE INDEX IF NOT EXISTS idx_conglomerate_logs_org ON conglomerate_logs(org_secure_code);
CREATE INDEX IF NOT EXISTS idx_conglomerate_logs_created ON conglomerate_logs(created_at DESC);

-- 欄位註解
COMMENT ON TABLE conglomerate_logs IS '集團操作日誌';
COMMENT ON COLUMN conglomerate_logs.conglomerate_secure_code IS '集團識別碼';
COMMENT ON COLUMN conglomerate_logs.org_secure_code IS '企業識別碼';
COMMENT ON COLUMN conglomerate_logs.action IS '操作類型: JOIN=加入, LEAVE=退出';
COMMENT ON COLUMN conglomerate_logs.operator_email IS '操作者信箱';
COMMENT ON COLUMN conglomerate_logs.description IS '操作描述';
