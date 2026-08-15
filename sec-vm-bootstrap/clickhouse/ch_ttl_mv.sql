-- =====================================================================
-- secstack ClickHouse：保留期分層 + 報表維度 MV（2026-08-08）
--
-- 背景：events 表原 TTL 只有 6 小時，明細留不住；長期只剩 events_per_minute，
-- 而它只有 minute / source_system / event_class 三個維度，
-- 使用者要的「依案件類型產出報表」做不出來。
--
-- 注意：events 表本身「已經有」完整維度欄位（actor_ip / actor_country /
-- finding_rule_id / target_url ...），缺的是 (a) 留存時間 (b) 帶維度的 rollup。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. events 明細分層保留
--    低嚴重度（Info/Low）留 30 天：供「這個 IP 上週做了什麼」的追查
--    中高嚴重度（Medium 以上）留 180 天：報表與事後鑑識主力
-- ---------------------------------------------------------------------
ALTER TABLE secstack.events
MODIFY TTL
    toDateTime(event_time) + INTERVAL 30 DAY DELETE WHERE severity_id <= 2,
    toDateTime(event_time) + INTERVAL 180 DAY DELETE WHERE severity_id > 2;

-- ---------------------------------------------------------------------
-- 2. 小時級維度 rollup（報表主力，留 2 年）
--    刻意不含 actor_ip：IP 基數高，另開 attacker_ip_daily 承接，
--    避免這張表被單一掃描來源撐爆而失去 rollup 的意義。
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS secstack.events_hourly_dim
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, source_system, event_class, severity_id, finding_rule_id, finding_rule_set, actor_country, target_host)
TTL toDateTime(hour) + INTERVAL 730 DAY
AS SELECT
    toStartOfHour(event_time)         AS hour,
    source_system,
    event_class,
    severity_id,
    finding_rule_id,
    finding_rule_set,
    actor_country,
    target_host,
    count()                           AS events,
    uniqState(actor_ip)               AS uniq_actors,
    uniqState(target_url)             AS uniq_urls
FROM secstack.events
GROUP BY hour, source_system, event_class, severity_id,
         finding_rule_id, finding_rule_set, actor_country, target_host;

-- ---------------------------------------------------------------------
-- 3. 攻擊來源 IP 日級 rollup（TOP N 攻擊者、國別分佈，留 2 年）
-- ---------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS secstack.attacker_ip_daily
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(day)
ORDER BY (day, actor_ip, source_system, event_class)
TTL toDateTime(day) + INTERVAL 730 DAY
AS SELECT
    toDate(event_time)                AS day,
    actor_ip,
    source_system,
    event_class,
    any(actor_country)                AS actor_country,
    count()                           AS events,
    countIf(severity_id >= 3)         AS mid_high_events,
    uniqState(finding_rule_id)        AS uniq_rules,
    uniqState(target_host)            AS uniq_targets
FROM secstack.events
GROUP BY day, actor_ip, source_system, event_class;
