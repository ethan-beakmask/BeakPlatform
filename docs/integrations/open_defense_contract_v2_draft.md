# Open Defense 整合契約 v2 -- 草稿

**版本**: v2.0-draft
**狀態**: 草稿，待 sec-vm 端對齊後定稿
**建立**: 2026-05-13
**最後現況對齊**: 2026-08-10（見 §0.5）
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

## 0.5 現況對齊（2026-08-10）

本草稿寫於 2026-05-13，此後平台側走了三個月的實作。**這一節只寫平台側可驗證的
事實**；sec-vm（`.20`）側的現況一律標為待確認，權威在
`/opt/Ethan_Lab/ITHome-2026/CLAUDE.md`。

### 這份草稿仍然有效

聚合下推、反向通道、Platform 只處理 incident 這三個方向**都還沒實施**，
草稿描述的仍是下一代架構，不是已完成的事。§2/§3/§4 的端點在平台側都不存在。

### 但有三件事改變了前提

**一、平台側自己做了聚合降噪（2026-07-16 起）**

`intake_service._find_mergeable_case()`：同 `actor_ip` + `finding_rule_id`、
60 分鐘窗內的事件併進既有案件，`od_event_count` 累加、severity 取 max。
這是 v1 架構下的補救，**緩解了案件爆量但沒有解決事件量**——
每包事件仍然要進 `od_intake_events` 並完整存 `raw_body`。
v2 的動機因此仍成立，只是急迫性下降。

**二、`?profile=` 機制讓 §2 可能不需要新端點（2026-08-10 起）**

`POST /api/open_defense/intake/native?profile=<code>` 收任意 JSON，
由 `od_payload_profiles` 描述怎麼解析。把 incident envelope 對上去是這樣：

| envelope 欄位 | profile 設定 |
|---|---|
| `incident_id` | `correlation_id_path` |
| `primary.severity_id` / `primary.actor.ip` / `primary.finding.rule_id` … | `field_map` 的軸線映射 |
| `aggregation.*` / `context.*` | 自動扁平化成 `aggregation.event_count` 這種 key，表單 TABS 直接綁 |
| `related_locators` | 陣列原樣保留在 form_data |

`duplicate` 回應語意也已經一致。**因此 §2.1 的 `/api/open_defense/v2/incidents`
是否還要另開，應在定稿前重新評估**——用一個 profile 就能收，
差別只在契約要不要明文凍結 envelope 的 schema（明文凍結有它的價值，
但那是契約層的決定，不是實作限制）。這會連帶簡化 §5 的遷移計畫。

**三、路由已改為規則式（2026-08-09 起）**

`od_form_template_mappings` 支援 priority + 條件 + `payload_kind`，
一條規則＝一種案件類型。v2 若採 envelope，路由條件可以直接寫
`primary.finding.rule_id` 這種點號路徑，不需要為 v2 另做一套分流。

### 仍未實作、且 v2 依賴的東西

- 反向通道（§3 查原文、§4 規則回饋）：平台側零實作。
  處置中心的「事件明細」目前是讀 `form_data` 內的明細陣列，不查 sec-vm
- `related_locators` 的消費端：平台收得下這個欄位，但沒有任何 UI 會去解析它
- `od_intake_events.raw_body` 仍完整存原文（§9 of raw store spec 說 v2 後只留 metadata）

### 定稿前要先確認的（除了 §6 原有五點）

6. ~~平台側是否真的要另開 `/v2/incidents` 端點~~
   → **2026-08-10 已決：不另開**，走 `?profile=` 收 envelope，§2.1 已改寫並附實測證據
7. 反向通道要不要做——沒有它，`related_locators` 只是死欄位

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

### 2.1 端點（2026-08-10 定案：不另開，走既有 native intake）

```
POST /api/open_defense/intake/native?profile=od_incident_envelope_v2
```

Headers 沿用 v1（HMAC + Intake Key）。

**原本規劃的 `POST /api/open_defense/v2/incidents` 已確認不必要，本節作廢。**
2026-08-10 實測：把 §2.2 的 envelope 原樣送進 native intake，
由 `od_payload_profiles` 的一筆設定描述解析方式即可，
證據在 `/opt/tmp/verify/20260810-v2-envelope-via-profile.log`：

| v2 契約要求 | 實測結果 |
|---|---|
| 200 + `case_secure_code` + `workflow_started`（§2.4） | 一致 |
| 重送回 `duplicate: true`（§2.4） | 一致，冪等鍵取自 `incident_id` |
| `primary` / `aggregation` / `context` / `detector_hint` 全部保留 | 全部進 `form_data`，key 為 `primary.finding.rule_id` 這種點號形式 |
| `related_locators` 不傳原文、只傳指標 | 陣列原樣保留 |

對應的 profile 設定（`correlation_id_path` 與 `field_map` 是全部所需）：

```json
{
  "code": "od_incident_envelope_v2",
  "correlation_id_path": "incident_id",
  "field_map": {
    "severity_id": "primary.severity_id",
    "actor_ip": "primary.actor.ip",
    "target_host": "primary.target.host",
    "source_system": "primary.source_system",
    "finding_rule_id": "primary.finding.rule_id",
    "occurred_at": "aggregation.last_seen"
  },
  "detail_path": "related_locators"
}
```

**契約層仍要凍結 §2.2 的 envelope schema**——sec-vm 端送什麼是契約，
平台端怎麼解析是實作。差別只在平台不需要為此多維護一個端點、一套限流、
一套分流規則。路由條件可直接寫 `primary.source_system` 這種點號路徑
（規則的 `payload_kind` 設 `native`）。

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

**Phase 1 已因 §2.1 定案而簡化**：平台側不需要開發新端點，
只要建一筆 `od_incident_envelope_v2` profile 與一條 `payload_kind=native`
的路由規則就具備接收能力（兩者都能在 `/open-defense/event-routing` 上設定，
不必改程式、不必重啟服務）。

| 階段 | 內容 | 時長 |
|---|---|---|
| Phase 1 | 建 profile + 路由規則，v1 並行 | 立即 |
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
