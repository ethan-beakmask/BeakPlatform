# Open Defense 整合契約

**版本**: v1.0
**最後更新**: 2026-05-09
**適用對象**: 外部安全堆疊整合方(Suricata / Coraza WAF / Falco / CrowdSec / Vector / 自家 detector)

---

## 1. 文件目的與邊界

本文件是 BeakPlatform 與**外部事件來源端**、**外部決策執行端**之間的**唯一整合契約**。
雙方各自實作可自由選擇技術棧,但介面必須符合本契約。

**BeakPlatform 在這個整合中扮演:**
- **案件流程權威**:接收事件 → 啟動表單流程 → 由人或自動化做出決策。
- **決策廣播表**:把決策結果落到一張共用 DB 表,任何執行端都可以拉取。

**BeakPlatform 不做:**
- 不主動推送決策(no outbound webhook)。執行端永遠**拉**(poll)。
- 不綁定特定廠牌(F5/PA/Cloudflare/CrowdSec 都只是字串標籤)。
- 不做 IDS 規則同步、不做 threat intel 訂閱(那是事件來源端自己的事)。

**本文件不揭露的內容:**
- BeakPlatform 內部模型、ORM、ResourceGateway、RLS policy 細節。整合方無需知道。

---

## 2. 整合拓樸

```
[事件來源端]                            [BeakPlatform]                       [決策執行端]
Suricata ─┐                                                                    ┌─ CrowdSec bridge
Coraza   ─┤                ┌──── /api/open_defense/intake ◄────┐             │
Falco    ─┼─► Vector ─────►│   (HMAC webhook, OCSF body)        │             │
CrowdSec ─┘  (正規化)       │                                    │             │
                            │           BeakPlatform                           │
                            │   ┌─────────────────────────┐                   │
                            │   │ 1. 寫 intake_event       │                   │
                            │   │ 2. 啟動表單 workflow      │                   │
                            │   │ 3. 人/自動 決策          │                   │
                            │   │ 4. 寫 defense_decisions │                   │
                            │   └─────────────────────────┘                   │
                            │                                                  │
                            │   GET  /api/open_defense/decisions      ◄───────┤ (poll)
                            │   PATCH /api/open_defense/decisions/<sc> ◄───────┤ (回報)
                            │                                                  │
                            └──────────────────────────────────────────────────┘
                                                                          ┌─ nftables executor
                                                                          ├─ Cloudflare API client
                                                                          └─ 自家 app blocklist
```

---

## 3. 認證機制

### 3.1 事件來源端 — HMAC Webhook 簽章

> **P2 遷移公告(2026-07-08)**:Intake Key 已併入平台級 API Key 體系,
> 管理介面改為 `/security/api-keys/`(scope: `od_intake`)。
> 既有 `ik_` 開頭的 key_id 與 secret **原樣沿用,整合方無需變更**;
> 新申請的 key 一律為 `ak_` 開頭。
> Headers 支援雙軌:平台標準 `X-BP-*`(建議)與舊 `X-OD-*`(deprecated,保留相容)。

每個事件來源端先向 BeakPlatform 申請一組 **API Key**(於 `/security/api-keys/` 建立,勾 od_intake 來源):

| 欄位 | 說明 |
|---|---|
| `key_id` | 公開識別碼,放在 HTTP header,例:`ak_a3f9c2e1`(舊 key 為 `ik_` 開頭) |
| `secret` | 32-byte 隨機密鑰,**僅在建立時顯示一次**,後續無法再取得。整合方需自行妥善保管。 |
| `scopes.od_intake.source_systems` | 此 key 允許宣稱的 `source_system` 值清單 |

**簽章演算法:**

```
canonical_string = "{timestamp}\n{request_body_raw}"
signature = HMAC-SHA256(secret, canonical_string)
header_value = "sha256=" + hex(signature)
```

注意:
- `timestamp` 必須**包含進簽章內容**,以防 replay 攻擊時重簽。
- `request_body_raw` 是原始位元組,**簽章前不得做 JSON 重序列化**(避免空白/欄位順序差異導致驗章失敗)。

### 3.2 決策執行端 — Service Account + 短期 JWT

每個執行端先向 BeakPlatform 申請一組 **Service Account**:

| 欄位 | 說明 |
|---|---|
| `sa_id` | 公開識別碼,例:`sa_executor_crowdsec_01` |
| `sa_secret` | 32-byte 隨機密鑰,僅在建立時顯示一次 |

**取得 JWT:**

```http
POST /api/open_defense/sa/login
Content-Type: application/json

{ "sa_id": "sa_executor_crowdsec_01", "sa_secret": "..." }

→ 200 OK
{ "access_token": "eyJ...", "expires_in": 900, "token_type": "Bearer" }
```

JWT 預設有效期 **15 分鐘**,過期需重新登入。整合方應在本地快取 token,過期前主動刷新。

後續所有決策 API 呼叫帶 `Authorization: Bearer <access_token>`。

---

## 4. 入口 API — 事件回報

### 4.1 端點

```
POST /api/open_defense/intake
```

### 4.2 必要 Headers

| Header | 範例 | 說明 |
|---|---|---|
| `Content-Type` | `application/json` | 必須 UTF-8 編碼 |
| `X-BP-Key-Id` | `ak_a3f9c2e1` | API Key 識別碼(平台標準,建議) |
| `X-BP-Timestamp` | `1762668000` | Unix 秒,**5 分鐘**內有效 |
| `X-BP-Signature` | `sha256=abc123...` | HMAC-SHA256 簽章(見 §3.1) |

舊 `X-OD-Key-Id` / `X-OD-Timestamp` / `X-OD-Signature` 三個 headers
仍可使用(deprecated),簽章格式相同。兩組同時出現時以 `X-BP-*` 為準。

### 4.3 Request Body Schema(OCSF-aligned)

```json
{
  "correlation_id": "01J9X8K2...",
  "source_system": "suricata",
  "event_class": "detection_finding",
  "occurred_at": "2026-05-09T10:00:00Z",
  "severity_id": 4,
  "confidence": 85,

  "finding": {
    "title": "SQLi attempt on /login",
    "summary": "OWASP CRS rule 942100 triggered",
    "rule_id": "942100",
    "rule_set": "OWASP CRS 4.0"
  },
  "actor": {
    "ip": "203.0.113.42",
    "asn": 15169,
    "country": "RU",
    "user_agent": "sqlmap/1.7"
  },
  "target": {
    "host": "app.example.com",
    "url": "/login",
    "service": "vm-100"
  },
  "evidence": {
    "raw_log_ref": {
      "type": "clickhouse",
      "locator": "logs.events/2026-05-09/abc123"
    },
    "snippet": "POST /login?id=1' OR '1'='1"
  },
  "detector_hint": {
    "action": "block",
    "ttl_sec": 3600,
    "note": "detector 建議,僅供 UI 參考,不參與 workflow 自動決策"
  }
}
```

#### 欄位規範

| 欄位 | 必填 | 型別 | 說明 |
|---|---|---|---|
| `correlation_id` | 是 | string(ULID 或 UUIDv4) | **全域唯一**冪等鍵。重複會回 409。 |
| `source_system` | 是 | string | 必須在此 key 的 `allowed_source_systems` 中 |
| `event_class` | 是 | enum | `detection_finding` / `network_activity` / `web_activity` / `process_activity` |
| `occurred_at` | 是 | ISO-8601 UTC | 事件實際發生時間 |
| `severity_id` | 是 | int 0-6 | OCSF severity:0=Unknown, 1=Informational, 2=Low, 3=Medium, 4=High, 5=Critical, 6=Fatal |
| `confidence` | 否 | int 0-100 | detector 信心度 |
| `finding.title` | 是 | string ≤200 | 案件標題 |
| `actor.ip` | 條件 | IPv4/IPv6 | `event_class` 為 network/web 時必填 |
| `evidence.raw_log_ref` | 否 | `{type, locator}` | 原始日誌指標,**不傳整段日誌**。`type` 自由字串,日後加新 log store 不必改 schema。 |
| `detector_hint` | 否 | object | **純資訊**。BeakPlatform 不會依此自動下決策,只在 UI 顯示。 |

### 4.4 Response

| 狀態碼 | 條件 | Body |
|---|---|---|
| 200 | 接收成功 | `{"success": true, "case_secure_code": "...", "workflow_started": true}` |
| 200 | 重複 correlation_id(冪等返回) | `{"success": true, "case_secure_code": "...", "duplicate": true}` |
| 400 | Body 不符 schema | `{"error": "validation_error", "details": [...]}` |
| 401 | 簽章錯 / timestamp 過期 / key 不存在 | `{"error": "auth_failed"}` |
| 403 | `source_system` 不在 key 允許清單 | `{"error": "source_not_allowed"}` |
| 429 | Rate limit | `{"error": "rate_limited", "retry_after": 30}` |

**注意 409 已不使用** — 重複 `correlation_id` 改回 200 並夾帶 `"duplicate": true`,讓來源端可安心重送。

### 4.5 Rate Limit

`/api/open_defense/*` 端點**獨立於平台全域 rate limit**,計數軸與額度如下:

| 端點 | 計數軸 | 預設額度 |
|---|---|---|
| `POST /api/open_defense/intake` | per `key_id`(從 `X-BP-Key-Id` 或舊 `X-OD-Key-Id` header) | 100 / min, 5000 / hour |
| `GET /api/open_defense/decisions` | per `sa_id`(從 JWT claim) | 60 / min, 3000 / hour, 50000 / day |
| `PATCH /api/open_defense/decisions/<sc>` | per `sa_id` | 300 / min |
| `POST /api/open_defense/sa/login` | per source IP | 10 / min(防憑證爆破) |

**要點:**
- 計數軸是 `key_id` / `sa_id`,**不是 IP**。多個執行端共用同一出口 IP 不會互相吃額度,整合端流量也不會吃到人類用戶的全域配額。
- 超過時回 429,並夾以下 headers:
  - `Retry-After: <秒>` — 建議等待秒數
  - `X-RateLimit-Limit: <額度>` — 該軸的上限
  - `X-RateLimit-Remaining: 0`
  - `X-RateLimit-Reset: <unix-ts>` — 下次重置時間
- 整合方應遵守 `Retry-After` 並做指數 backoff,不要硬撞。
- 額度可向 BeakPlatform 管理員申請調整,但建議先檢視自身發送策略是否合理。

---

## 5. 出口 API — 決策訂閱

### 5.1 拉取待執行決策

```http
GET /api/open_defense/decisions?status=pending&enforcement_point=crowdsec&limit=100
Authorization: Bearer <jwt>
```

#### 查詢參數

| 參數 | 必填 | 說明 |
|---|---|---|
| `status` | 否 | `pending`(預設) / `applied` / `expired` / `failed` |
| `enforcement_point` | 否 | 只取 `enforcement_points` 含此值的決策(例:`crowdsec`) |
| `limit` | 否 | 預設 100,上限 500 |
| `since` | 否 | ISO-8601,只取此時間之後建立的 |

#### Response

```json
{
  "decisions": [
    {
      "secure_code": "od_dec_8f2a...",
      "action": "block",
      "target_type": "ip",
      "target_value": "203.0.113.42",
      "enforcement_points": ["crowdsec", "nftables"],
      "severity": "high",
      "ttl_seconds": 3600,
      "expires_at": "2026-05-09T11:00:00Z",
      "reason": "SQLi attempt — case OD-2026-0042",
      "decided_at": "2026-05-09T10:00:00Z",
      "case_secure_code": "fc_..."
    }
  ],
  "next_since": "2026-05-09T10:05:00Z"
}
```

### 5.2 回報執行結果

```http
PATCH /api/open_defense/decisions/<secure_code>
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "status": "applied",
  "applied_by": "crowdsec-bridge@sec-vm-01",
  "application_result": {
    "crowdsec": {"ok": true, "decision_id": 12345},
    "nftables": {"ok": true, "rule_handle": 89}
  }
}
```

#### 允許的狀態轉換

| 從 | 到 | 條件 |
|---|---|---|
| `pending` | `picked_up` | 執行端開始處理(可選,做樂觀鎖時用) |
| `pending` / `picked_up` | `applied` | 執行成功 |
| `pending` / `picked_up` | `partial` | 部分 enforcement_point 成功 |
| `pending` / `picked_up` | `failed` | 全部失敗,需附 `error_message` |

**禁止**自行寫入 `expired` 或 `revoked`,這由 BeakPlatform 排程處理。

### 5.3 推薦輪詢策略

- **正常**:每 5 秒拉一次 `status=pending`(= 12/min, 720/hour,在預設額度內留充足餘裕)。
- **長連線**:本契約 v1 不支援 WebSocket / SSE,僅輪詢。
- **樂觀鎖**:多個執行端同時跑時,先 `PATCH status=picked_up` 再實際執行,避免重複處理。
- **退避**:遇 429 時依 `Retry-After` 等待,不要立即重試。連續 3 次 429 應拉長到 30 秒輪詢並告警運維。

### 5.4 Rate Limit 與輪詢預算

決策 API 的計數軸是 `sa_id`(從 JWT 內取),不是 IP。這代表:

- 多個執行端共用同一出口 IP **不會互相吃額度**,各自有獨立配額。
- 一個 SA 同時被多台機器使用會共用配額;跨機器並行請申請多個 SA。
- JWT 過期重新登入(`POST /api/open_defense/sa/login`)走 **per IP** 計數,15 分鐘刷一次遠低於上限,不需擔心。

預算對照(預設值,5 秒輪詢):

| 操作 | 速率 | 月用量 | 是否安全 |
|---|---|---|---|
| 拉決策(空回應) | 12/min, 17,280/day | — | **超日上限 50,000 仍有餘裕**(單一 SA) |
| 拉決策(每次 50 筆) | 12/min | — | 同上,bandwidth 才是限制因素 |
| 回報執行結果 | 視決策量 | — | 300/min 對應每秒 5 筆,正常單機足夠 |

---

## 6. 決策語意

### 6.1 Action

| `action` | 語意 | 典型 enforcement |
|---|---|---|
| `block` | 阻擋指定目標 | 防火牆 drop / WAF deny / 應用層 blocklist |
| `unblock` | 解除阻擋(對應之前的 block) | 移除規則 |
| `allow` | 顯式放行(可覆蓋 block) | 白名單 |
| `escalate` | 提升偵測級別,不直接阻擋 | log enrichment / SIEM tag |
| `observe` | 僅觀察,不動作 | 留下追蹤標記 |

### 6.2 Target Type

| `target_type` | `target_value` 格式 |
|---|---|
| `ip` | IPv4 或 IPv6 單一位址 |
| `cidr` | CIDR 表示法,例 `203.0.113.0/24` |
| `domain` | FQDN,例 `bad.example.com` |
| `url` | 完整 URL,例 `https://app.example.com/login` |
| `asn` | 數字字串,例 `15169` |
| `country` | ISO 3166-1 alpha-2,例 `RU` |
| `user_agent` | UA 字串(完整比對) |
| `jwt_sub` | JWT subject claim |

### 6.3 Enforcement Points

**自由字串**,但建議用以下標準值以利跨整合協作:

`crowdsec` / `nftables` / `iptables` / `cloudflare` / `fastly` / `aws_waf` /
`app_internal` / `siem_tag` / `email_relay`

執行端只處理 `enforcement_points` 含**自己標籤**的決策,其他略過。

### 6.4 TTL 與過期

- `ttl_seconds` 為 NULL 表示**永久**。
- BeakPlatform 排程每分鐘掃描 `status='applied' AND expires_at < now()`,自動產生**對應的 unblock 決策**(同一 target,action='unblock'),由執行端拉取後撤銷。
- 執行端**不可**自行判斷過期就撤,必須等 BeakPlatform 下達 unblock 決策。

---

## 7. 錯誤處理與重試

### 7.1 事件來源端

- HTTP 5xx / 網路錯誤:**指數 backoff 重試**(1s, 2s, 4s, ..., 上限 5 分鐘),最多 24 小時。
- HTTP 4xx(401/403/422):**不要重試**,記錯誤 log 並告警運維。
- correlation_id 必須在來源端持久化,重試時用同一個 ID(冪等)。

### 7.2 決策執行端

- 拉取失敗:5 秒後重試,JWT 過期則重新登入。
- 執行失敗:回報 `status=failed` 並附 `error_message`,**不要無限重試**。BeakPlatform 端會在 UI 顯示失敗,由人工或 workflow 處理。

---

## 8. 安全注意事項

1. **HMAC secret 與 SA secret 一律不得寫入版控**,使用環境變數或密鑰管理服務。
2. **時間同步**:整合方主機與 BeakPlatform 時鐘差距須 < 60 秒,否則 timestamp 驗證會失敗。建議啟用 NTP。
3. **TLS 必填**:正式環境一律 HTTPS,憑證驗證不可關閉。內網測試環境可暫用 HTTP,但禁止用於正式資料。
4. **不要在 webhook body 傳完整 PII / 完整原始日誌**,只傳 `raw_log_ref` 指標。
5. **decision 的 `target_value` 屬高權限資訊**,執行端拿到後不得再轉發給第三方。

---

## 9. 版本與相容性

- 本文件版本以 semver 管理。
- **breaking change** 會提前 30 天公告,並提供雙版本平行期。
- API 端點預留 `/v2/...` 命名空間,目前 `/api/open_defense/...` 視為 v1。

---

## 10. 申請流程

1. 整合方提交申請(寄信至 BeakPlatform 管理員),說明:
   - 事件來源系統清單(對應 `source_system` 值)
   - 預計事件量級
   - 執行端類型(對應 `enforcement_points` 值)
2. BeakPlatform 管理員建立 Intake Key 與 Service Account,**密鑰透過安全管道一次性傳遞**。
3. 整合方在測試環境完成串接測試後再上線。

---

## 附錄 A:範例事件(SQLi 偵測)

```bash
TIMESTAMP=$(date +%s)
BODY='{"correlation_id":"01J9X8K2ABCD","source_system":"coraza","event_class":"web_activity","occurred_at":"2026-05-09T10:00:00Z","severity_id":4,"finding":{"title":"SQLi","rule_id":"942100","rule_set":"OWASP CRS 4.0"},"actor":{"ip":"203.0.113.42"},"target":{"host":"app.example.com","url":"/login"}}'
SIG=$(printf '%s\n%s' "$TIMESTAMP" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $2}')

curl -X POST https://beakplatform.example.com/api/open_defense/intake \
  -H "Content-Type: application/json" \
  -H "X-OD-Key-Id: ik_a3f9c2e1" \
  -H "X-OD-Timestamp: $TIMESTAMP" \
  -H "X-OD-Signature: sha256=$SIG" \
  -d "$BODY"
```

## 附錄 B:範例執行端輪詢

```python
import time, requests

token = login()  # 取 JWT

while True:
    r = requests.get(
        "https://beakplatform.example.com/api/open_defense/decisions",
        headers={"Authorization": f"Bearer {token}"},
        params={"status": "pending", "enforcement_point": "crowdsec", "limit": 50},
        timeout=10,
    )
    if r.status_code == 401:
        token = login()
        continue
    for d in r.json()["decisions"]:
        ok = apply_to_crowdsec(d)
        requests.patch(
            f"https://beakplatform.example.com/api/open_defense/decisions/{d['secure_code']}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "status": "applied" if ok else "failed",
                "applied_by": "crowdsec-bridge@sec-vm-01",
                "application_result": {"crowdsec": {"ok": ok}},
            },
        )
    time.sleep(5)
```
