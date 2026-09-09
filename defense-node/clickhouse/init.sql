-- =============================================================
-- Open Defense — ClickHouse schema
-- =============================================================
-- One wide events table (raw OCSF JSON + extracted hot columns)
-- + one findings table for rule-matched / decided events.
-- Vector writes to events;  od-bridge writes findings on decision PATCH.
-- =============================================================

CREATE TABLE IF NOT EXISTS secstack.events
(
    event_time      DateTime64(3, 'UTC')  CODEC(Delta, ZSTD(3)),
    ingested_at     DateTime64(3, 'UTC')  DEFAULT now64() CODEC(Delta, ZSTD(3)),
    correlation_id  String                CODEC(ZSTD(3)),
    source_system   LowCardinality(String),
    event_class     LowCardinality(String),
    severity_id     UInt8,
    confidence      UInt8 DEFAULT 0,

    actor_ip        IPv6,
    actor_asn       UInt32 DEFAULT 0,
    actor_country   FixedString(2) DEFAULT '\0\0',
    actor_ua        String CODEC(ZSTD(3)),
    -- PF-105 2026-08-15：完整 XFF 鏈原文（證據欄位，不參與 SLA/聚合/風險分數判定，
    -- 那些一律看 actor_ip）。既有表要另外 ALTER TABLE ADD COLUMN，這裡只影響新建庫。
    -- 型別/DEFAULT/CODEC 順序刻意採 ALTER TABLE 也接受的寫法（DEFAULT 在 CODEC 前）
    -- ——CODEC 在前、DEFAULT 在後那個順序在 ALTER ADD COLUMN 會噴 SYNTAX_ERROR
    -- （已在 .20 實測過，見 PF-105 驗收 log）。
    actor_xff       String DEFAULT '' CODEC(ZSTD(3)),

    target_host     String CODEC(ZSTD(3)),
    target_url      String CODEC(ZSTD(3)),
    target_service  LowCardinality(String),

    finding_title   String CODEC(ZSTD(3)),
    finding_rule_id String CODEC(ZSTD(3)),
    finding_rule_set LowCardinality(String),

    raw             String CODEC(ZSTD(7))
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(event_time)
ORDER BY (event_class, source_system, event_time, correlation_id)
TTL toDateTime(event_time) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS secstack.findings
(
    decided_at      DateTime64(3, 'UTC')  CODEC(Delta, ZSTD(3)),
    case_secure_code String              CODEC(ZSTD(3)),
    decision_secure_code String          CODEC(ZSTD(3)),
    action          LowCardinality(String),
    target_type     LowCardinality(String),
    target_value    String CODEC(ZSTD(3)),
    enforcement_points Array(LowCardinality(String)),
    severity        LowCardinality(String),
    ttl_seconds     UInt32 DEFAULT 0,
    reason          String CODEC(ZSTD(3)),
    decided_via     LowCardinality(String),
    apply_status    LowCardinality(String),
    apply_result    String CODEC(ZSTD(3))
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(decided_at)
ORDER BY (decided_at, decision_secure_code)
TTL toDateTime(decided_at) + INTERVAL 365 DAY;

-- realtime aggregate: per-source/class events per minute
CREATE MATERIALIZED VIEW IF NOT EXISTS secstack.events_per_minute
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(minute) ORDER BY (minute, source_system, event_class)
AS
SELECT
    toStartOfMinute(event_time) AS minute,
    source_system,
    event_class,
    count() AS events,
    countIf(severity_id >= 4) AS high_sev_events
FROM secstack.events
GROUP BY minute, source_system, event_class;
