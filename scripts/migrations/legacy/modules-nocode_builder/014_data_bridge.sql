-- 014_data_bridge.sql
-- DataBridge: PG ↔ SQLite 資料橋接設定與操作日誌
--
-- 1. dc_sub_systems 加 bridge_rules JSONB（橋接規則定義）
-- 2. dc_bridge_logs 記錄每次橋接操作（審計追蹤）

-- bridge_rules: 子系統的橋接規則設定（Studio 可配置）
ALTER TABLE dc_sub_systems
    ADD COLUMN IF NOT EXISTS bridge_rules JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN dc_sub_systems.bridge_rules IS '資料橋接規則 JSON 陣列，每條 rule 包含 source/target/field_mapping/trigger_type';

-- bridge_logs: 橋接操作審計日誌
CREATE TABLE IF NOT EXISTS dc_bridge_logs (
    id              SERIAL PRIMARY KEY,
    secure_code     VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,

    -- 歸屬
    sub_system_secure_code VARCHAR(32) NOT NULL,
    rule_id                VARCHAR(64),

    -- 方向: 'publish' | 'update' | 'collect'
    direction       VARCHAR(20) NOT NULL,

    -- 來源 / 目標
    source_db       VARCHAR(20) NOT NULL,
    source_table    VARCHAR(128) NOT NULL,
    target_db       VARCHAR(20) NOT NULL,
    target_table    VARCHAR(128) NOT NULL,

    -- 操作記錄
    record_key      JSONB,
    records_affected INTEGER NOT NULL DEFAULT 0,
    field_mapping   JSONB,

    -- 狀態: 'success' | 'failed'
    status          VARCHAR(20) NOT NULL DEFAULT 'success',
    error_message   TEXT,

    -- 操作者
    operator_secure_code VARCHAR(32),

    -- 時間
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 軟刪除
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bridge_logs_sub_system
    ON dc_bridge_logs (sub_system_secure_code);
CREATE INDEX IF NOT EXISTS idx_bridge_logs_org
    ON dc_bridge_logs (org_secure_code);
CREATE INDEX IF NOT EXISTS idx_bridge_logs_direction
    ON dc_bridge_logs (direction);
CREATE INDEX IF NOT EXISTS idx_bridge_logs_created
    ON dc_bridge_logs (created_at DESC);
