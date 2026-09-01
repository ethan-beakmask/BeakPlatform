-- 107: AiAgent 節點用量記錄與企業配額預設
--
-- 對應 handler: modules/form_workflow/services/node_handlers/ai_agent_handler.py
-- 對應 service: modules/form_workflow/services/ai_usage_service.py
--
-- 設計理由：
--   1. AiAgent 會呼叫本機 claude CLI，回應 envelope 內含 token 與 total_cost_usd。
--      這些數字是依標準 API 牌價換算的「估算成本」，不是實際扣款或帳單。
--   2. 成功、失敗與被配額擋下的嘗試都要留痕。失敗若已有 envelope，仍可能已花 token；
--      blocked 則成本為 0，供事後稽核誰在反覆撞牆。
--   3. 配額依企業時區的今日／本月切分，由 service 以 org_secure_code 過濾並配合
--      PostgreSQL advisory lock 做「檢查 -> 佔位」序列化，避免併發穿透。
--
-- 使用方式：
--   PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev \
--     -f scripts/migrations/107_ai_agent_usage_quota.sql
-- 冪等，可重複執行。

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. AiAgent 用量記錄表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fw_ai_usage_records (
    id                                SERIAL PRIMARY KEY,
    secure_code                       VARCHAR(32)   NOT NULL UNIQUE DEFAULT generate_secure_code(),
    org_secure_code                   VARCHAR(32)   NOT NULL,
    workflow_instance_secure_code     VARCHAR(32),
    form_instance_secure_code         VARCHAR(32),
    node_id                           VARCHAR(64),
    node_name                         VARCHAR(200),
    node_queue_secure_code            VARCHAR(32),
    model                             VARCHAR(100),
    status                            VARCHAR(20)   NOT NULL,
    input_tokens                      INTEGER       NOT NULL DEFAULT 0,
    output_tokens                     INTEGER       NOT NULL DEFAULT 0,
    cache_creation_input_tokens       INTEGER       NOT NULL DEFAULT 0,
    cache_read_input_tokens           INTEGER       NOT NULL DEFAULT 0,
    cost_usd                          NUMERIC(14,8) NOT NULL DEFAULT 0,
    duration_ms                       INTEGER       NOT NULL DEFAULT 0,
    num_turns                         INTEGER       NOT NULL DEFAULT 0,
    model_usage                       JSONB,
    error_message                     TEXT,
    started_at                        TIMESTAMP     NOT NULL,
    finished_at                       TIMESTAMP,
    created_at                        TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at                        TIMESTAMP     NOT NULL DEFAULT NOW(),
    is_deleted                        BOOLEAN       NOT NULL DEFAULT FALSE,
    deleted_at                        TIMESTAMP
);

COMMENT ON TABLE fw_ai_usage_records IS
    'AiAgent 節點每次嘗試執行的用量記錄。成功、失敗與配額 blocked 都會記錄，供配額判定與稽核。';
COMMENT ON COLUMN fw_ai_usage_records.org_secure_code IS
    '租戶識別碼；所有查詢必須以此作為實際 filter 條件。';
COMMENT ON COLUMN fw_ai_usage_records.status IS
    'running=已通過配額並佔位；success=CLI 執行且輸出驗證成功；failed=CLI 有執行嘗試但失敗或輸出作廢；blocked=配額或停用阻擋，未執行且不計入配額。';
COMMENT ON COLUMN fw_ai_usage_records.cost_usd IS
    'claude CLI envelope 回報的標準 API 牌價估算成本（USD），不是實際扣款或帳單金額。';
COMMENT ON COLUMN fw_ai_usage_records.model_usage IS
    'claude CLI envelope 的 modelUsage 原樣保留，可能包含多個 model key。';
COMMENT ON COLUMN fw_ai_usage_records.started_at IS
    '執行開始或 blocked 發生時間，naive UTC。';
COMMENT ON COLUMN fw_ai_usage_records.finished_at IS
    '執行完成或 blocked 完成時間，naive UTC。';

CREATE INDEX IF NOT EXISTS ix_fw_ai_usage_org_started
    ON fw_ai_usage_records (org_secure_code, started_at);

CREATE INDEX IF NOT EXISTS ix_fw_ai_usage_wi
    ON fw_ai_usage_records (workflow_instance_secure_code);

CREATE UNIQUE INDEX IF NOT EXISTS ux_fw_ai_usage_secure_code
    ON fw_ai_usage_records (secure_code);

-- ---------------------------------------------------------------------------
-- 2. 系統層預設配額
-- ---------------------------------------------------------------------------
INSERT INTO system_settings
    (secure_code, key, value, value_type, description, category,
     created_at, updated_at, is_deleted)
VALUES
    (
        generate_secure_code(),
        'ai_node_defaults',
        '{"enabled": true, "daily_max_runs": 50, "monthly_max_runs": 1000, "daily_max_cost_usd": 1.0, "monthly_max_cost_usd": 20.0}',
        'json',
        'AiAgent 節點的系統層預設配額；企業可在 organizations.settings 以 ai_node_* 覆寫。',
        'ai_node',
        NOW(),
        NOW(),
        FALSE
    )
ON CONFLICT (key) DO NOTHING;

COMMIT;
