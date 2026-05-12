# Open Defense 整合契約 v2 -- 草稿

**版本**: v2.0-draft
**狀態**: 草稿，待 sec-vm 端對齊後定稿
**建立**: 2026-05-13
**對 v1 的關係**: v1.0 端點維持運作並標 deprecated，**12 個月雙版本平行期**後下線

---

## 0. v2 對 v1 的核心變化

| 主題 | v1 | v2 |
|---|---|---|
| 推送單位 | single event | **incident envelope**（已聚合） |
| 聚合責任 | 未定義 | **明確由 sec-vm 端負責** |
| 反向通道 | 無 | **新增**：Platform → sec-vm 的 read-only raw log API + rule feedback API |
| 案件數量級 | 與事件量同（百萬/月） | **降至 incident 量**（千~萬/月） |
| OCSF 對齊 | event_class 多種 | event_class 改放在 incident.primary 內 |

**設計動機**：v1 的「single event push」造成 Platform 端案件爆量、SQL 漸鎖死（公司端 ELK/Splunk 拉 SQL 已驗證此反模式）。v2 把聚合下推到 sec-vm，Platform 只處理 incident。

---

## 1. 架構拓樸（v2）

```
[多源資料]              [sec-vm: 192.168.0.20]                  [Platform: 192.168.0.16]
Suricata/Coraza/Falco ─┐
ELK/Splunk export    ─┤
email/csv/xlsx       ─┼─► Layer 1 parser
MariaDB/SQLite       ─┤    ↓
JSON/其他            ─┘ Layer 2 normalize (OCSF)
                          ↓
                       Layer 3 enrich (GeoIP/ASN/TI)
                          ↓
                       Layer 4 correlate (5min 視窗)         POST /api/open_defense/v2/incidents
                          ↓                       ─HMAC─►   (incident envelope)
                       raw_store (ClickHouse)                    │
                       (Layer 0 全保留)            ◄─JWT pull─   │
                          ▲                                      ▼
                          │                              ┌──────────────┐
                          └──── GET /raw/<locator> ◄─────│ Platform     │
                                POST /rule_feedback ◄────│ 案件 UI/處置  │
                                                         └──────────────┘
                                                                │
                                                         GET decisions ◄─── executor
                                                         (v1 端點不變)
```

---

## 2. Incident Envelope -- 入口 API

### 2.1 端點

```
POST /api/open_defense/v2/incidents
```

Headers 沿用 v1（HMAC + Intake Key），改為 v2 端點獨立計數。

### 2.2 Body Schema

```json
{
  "incident_id": "inc_01J9X8K2ABCD",
  "tenant_hint": "beluga",

  "aggregation": {
    "window_seconds": 300,
    "event_count": 523,
    "first_seen": "2026-05-13T01:00:00Z",
    "last_seen": "2026-05-13T01:04:58Z",
    "dedup_key": "actor.ip:203.0.113.42|rule:942100"
  },

  "primary": {
    "source_system": "coraza",
    "event_class": "web_activity",
    "severity_id": 4,
    "confidence": 85,
    "finding": { "title": "...", "rule_id": "942100", "rule_set": "..." },
    "actor": { "ip": "203.0.113.42", "asn": 15169, "country": "RU", "user_agent": "sqlmap/1.7" },
    "target": { "host": "...", "url": "/login", "service": "vm-100" },
    "evidence": { "snippet": "..." }
  },

  "related_locators": [
    { "type": "clickhouse", "locator": "raw_events/2026-05-13/inc_01J...", "count": 523 }
  ],

  "context": {
    "mitre_techniques": ["T1190"],
    "prior_incidents_24h": 3,
    "ti_tags": ["known_scanner"]
  },

  "detector_hint": { "action": "block", "ttl_sec": 3600 }
}
```

### 2.3 欄位規範差異（vs v1）

| 欄位 | 規範 |
|---|---|
| `incident_id` | 取代 v1 的 `correlation_id`，**全域唯一冪等鍵** |
| `aggregation.dedup_key` | sec-vm 端聚合判斷邏輯的留底（人類可讀） |
| `primary` | 代表性事件，schema 同 v1 body |
| `related_locators` | 指回 raw store 的指標陣列，**不傳原文** |
| `context.prior_incidents_24h` | sec-vm 端富化結果（同 actor.ip 過去 24h 案件數） |

### 2.4 Response

| 狀態碼 | Body |
|---|---|
| 200 | `{"success": true, "case_secure_code": "...", "workflow_started": true}` |
| 200（重複） | `{"success": true, "case_secure_code": "...", "duplicate": true}` |
| 4xx/5xx | 同 v1 §4.4 |

---

## 3. 反向通道 -- 原文查詢 API

**Platform → sec-vm 方向。** 由 sec-vm 端開 endpoint，Platform 端持 SA 憑證呼叫。

### 3.1 端點（在 sec-vm 上）

```
GET  https://sec-vm.internal/api/raw_query?locator=<locator>&limit=100
POST https://sec-vm.internal/api/raw_query/batch   (locator 陣列)
```

### 3.2 認證

Platform 端註冊為 sec-vm 的 Service Account（角色互換 v1 的方向），取 JWT，15 分鐘有效。

### 3.3 Response

```json
{
  "locator": "raw_events/2026-05-13/inc_01J...",
  "events": [
    { "ts": "...", "source_system": "...", "raw_payload": { ...原始 OCSF event... } }
  ],
  "truncated": false
}
```

### 3.4 Rate Limit

per Platform-SA：`60/min, 1000/hour`。案件詳情頁開啟才呼叫，正常 UI 用量遠低於此。

### 3.5 失敗處理

sec-vm 不可達或 locator 失效時，Platform UI 顯示「原文暫不可查」並仍允許處置流程繼續（locator 不阻塞案件流轉）。

---

## 4. 反向通道 -- 規則回饋 API

### 4.1 設計原則

**不是每筆誤判都回送**。Platform 端標記誤判 → 累積 → 人判斷「修規則 / 加白名單 / 容忍」→ 只有「修規則」決議才呼叫此 API。

### 4.2 端點（在 sec-vm 上）

```
POST https://sec-vm.internal/api/rule_feedback
```

### 4.3 Body

```json
{
  "feedback_id": "fb_01J...",
  "rule_id": "942100",
  "rule_set": "OWASP CRS 4.0",
  "verdict": "false_positive",
  "scope": "rule_revision",
  "evidence_incidents": ["inc_...", "inc_..."],
  "operator_note": "規則對合法的 SQL 教學頁誤觸",
  "decided_by": "soc-l2-ethan"
}
```

`scope` 列舉：

| 值 | 語意 |
|---|---|
| `rule_revision` | 建議修規則本體 |
| `whitelist_target` | 對特定 target 加白名單 |
| `whitelist_actor` | 對特定 actor 加白名單 |
| `tolerate` | 容忍，不修規則（仍回送做統計） |

### 4.4 Response

```json
{ "received": true, "feedback_secure_code": "...", "queued_for_review_by": "detector_owner" }
```

sec-vm 端**不自動套用**，只入規則檢討佇列。實際修規則仍由 detector 維運者人工決定。

---

## 5. v1 → v2 遷移計畫

| 階段 | 內容 | 時長 |
|---|---|---|
| Phase 1 | v2 端點上線，v1 並行 | 立即 |
| Phase 2 | sec-vm 端遷移到 v2 incident push，v1 端點記錄 deprecation log | T+1 月 |
| Phase 3 | v1 端點回 200 + warning header，仍接受 | T+6 月 |
| Phase 4 | v1 端點下線 | T+12 月 |

Decision API (`GET/PATCH /api/open_defense/decisions/...`) 不在此範圍，**v2 不動 decision API**。

---

## 6. 待 sec-vm 端確認的決策點

1. **Layer 4 聚合視窗**：5 分鐘是否合理？某些攻擊（慢速暴破）可能需要 1 小時視窗
2. **dedup_key 規則**：`actor.ip + rule_id` 是否足夠？要不要納入 target？
3. **raw store 路徑命名**：`raw_events/<date>/<incident_id>` 還是 `raw_events/<source>/<date>/...`
4. **反向通道 endpoint 部署**：sec-vm 上跑 nginx + Flask？還是直接打 ClickHouse？前者較好做 audit 與 rate limit
5. **規則回饋的審核者**：sec-vm 端誰負責看 review queue？（影響 §4.4 的 `queued_for_review_by` 值）

---

## 7. 不變的事

- HMAC + Intake Key 機制（§3.1 of v1）不變
- Decision API（§5 of v1）不變，executor 端無感
- OCSF 對齊（§4.3 of v1 欄位）不變，只是搬到 `incident.primary` 之下
- Rate limit 哲學（per key/SA 而非 per IP）不變
