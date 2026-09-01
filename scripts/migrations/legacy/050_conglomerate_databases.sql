-- 050: 集團共享資料庫相關表
-- 建立 FwConglomerateDatabase + FwConglomerateTableRegistry

-- 集團共享資料庫登記表
CREATE TABLE IF NOT EXISTS fw_conglomerate_databases (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    conglomerate_secure_code VARCHAR(32) NOT NULL UNIQUE,
    conglomerate_id INTEGER NOT NULL UNIQUE,
    db_name VARCHAR(100) NOT NULL UNIQUE,
    db_host VARCHAR(255) DEFAULT 'localhost',
    db_port INTEGER DEFAULT 5432,
    admin_user VARCHAR(100) NOT NULL,
    admin_password_enc TEXT NOT NULL,
    member_user VARCHAR(100) NOT NULL,
    member_password_enc TEXT NOT NULL,
    is_ready BOOLEAN NOT NULL DEFAULT FALSE,
    last_credential_rotation TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fw_cg_db_cg_sc
    ON fw_conglomerate_databases (conglomerate_secure_code);

-- 集團共享 DB 表格登記表（追蹤建立者企業）
CREATE TABLE IF NOT EXISTS fw_conglomerate_table_registry (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    conglomerate_secure_code VARCHAR(32) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    creator_org_secure_code VARCHAR(32) NOT NULL,
    creator_org_name VARCHAR(255),
    spec_secure_code VARCHAR(32),
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fw_cg_table_reg_cg_sc
    ON fw_conglomerate_table_registry (conglomerate_secure_code);
CREATE INDEX IF NOT EXISTS idx_fw_cg_table_reg_creator
    ON fw_conglomerate_table_registry (creator_org_secure_code);
