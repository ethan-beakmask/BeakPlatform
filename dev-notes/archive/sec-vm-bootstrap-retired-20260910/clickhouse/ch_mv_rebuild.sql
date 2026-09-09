-- 重建兩個 MV 並從 events 回填（2026-08-08）
-- 原因：回灌試了兩輪，MV 是獨立表、不受 events 的 TTL 刪除影響，
-- 於是 MV 累積到 2249 筆而 events 只有 2115 筆。重建一次對齊。

DROP TABLE IF EXISTS secstack.attacker_ip_daily;
DROP TABLE IF EXISTS secstack.events_hourly_dim;

CREATE MATERIALIZED VIEW secstack.events_hourly_dim
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

CREATE MATERIALIZED VIEW secstack.attacker_ip_daily
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

-- 回填歷史（MV 只對建立後的 INSERT 生效，既有資料要手動灌）
INSERT INTO secstack.events_hourly_dim
SELECT
    toStartOfHour(event_time) AS hour,
    source_system, event_class, severity_id,
    finding_rule_id, finding_rule_set, actor_country, target_host,
    count() AS events,
    uniqState(actor_ip) AS uniq_actors,
    uniqState(target_url) AS uniq_urls
FROM secstack.events
GROUP BY hour, source_system, event_class, severity_id,
         finding_rule_id, finding_rule_set, actor_country, target_host;

INSERT INTO secstack.attacker_ip_daily
SELECT
    toDate(event_time) AS day,
    actor_ip, source_system, event_class,
    any(actor_country) AS actor_country,
    count() AS events,
    countIf(severity_id >= 3) AS mid_high_events,
    uniqState(finding_rule_id) AS uniq_rules,
    uniqState(target_host) AS uniq_targets
FROM secstack.events
GROUP BY day, actor_ip, source_system, event_class;
