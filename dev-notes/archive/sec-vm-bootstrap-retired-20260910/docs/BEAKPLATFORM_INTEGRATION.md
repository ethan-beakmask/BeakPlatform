# BeakPlatform Integration — 對接細節與已知行為

> 權威契約文件:`/opt/open_defense_contract.md`(BeakPlatform 端發布,本檔案是「實測已知」摘要與避坑筆記)

## URL 結構

所有端點都在 nginx 反代後,**必須**含 `/beakplatform` 前綴:

```
POST  /beakplatform/api/open_defense/intake
POST  /beakplatform/api/open_defense/sa/login
GET   /beakplatform/api/open_defense/decisions
PATCH /beakplatform/api/open_defense/decisions/<secure_code>
```

> ⚠️ 直接打 `/api/open_defense/intake`(沒 `/beakplatform` 前綴)會 404。

## Intake API(契約 §4)

### Headers
| Header | 範例 | 說明 |
|---|---|---|
| `Content-Type` | `application/json` | UTF-8 |
| `X-OD-Key-Id` | `ik_<redacted>` | 從 `INTAKE_KEY_ID` |
| `X-OD-Timestamp` | `1762668000` | Unix 秒,5 分鐘內有效,**簽章內也帶這個值** |
| `X-OD-Signature` | `sha256=abc123...` | `sha256=` + hex(HMAC-SHA256(secret_raw, "{ts}\n{body_raw}")) |

`secret_raw` 是 base64url 解碼後的 32 byte。**不要**用 base64 字串本身去簽。

### Body schema(契約 §4.3 摘錄)

最小 working 例:
```json
{
  "correlation_id": "uuid-or-ulid",
  "source_system": "coraza|suricata|falco|crowdsec|vector",
  "event_class": "web_activity|network_activity|process_activity|detection_finding",
  "occurred_at": "2026-05-09T03:00:00Z",
  "severity_id": 0,
  "finding": {"title": "...", "rule_id": "...", "rule_set": "..."},
  "actor":  {"ip": "..."},
  "target": {"host": "...", "url": "..."}
}
```

`severity_id` OCSF 規範 0-6:
- 0 Unknown / 1 Informational / 2 Low / 3 Medium / 4 High / 5 Critical / 6 Fatal

### 回應碼

| Code | 意義 |
|---|---|
| 200 + `duplicate:false` | 接收成功,新案件已建,workflow 啟動 |
| 200 + `duplicate:true` | `correlation_id` 重送,**回前一筆的** `case_secure_code`(冪等) |
| 400 | schema 錯誤 |
| 401 | 簽章/timestamp 失敗 |
| 403 | `source_system` 不在此 key 的 `allowed_source_systems` |
| 422 | `event_class` 沒 mapping 到任何 form template |
| 429 | 限速(per `key_id`,100/min,5000/hour) |
| 500 | BP 內部錯誤(已知:`fw_workflow_instances.execution_code` race;**已修**) |

> 早期 BP 端尚未把所有 event_class 都 mapping 上,我們提供的 `web_activity` 已通,`network_activity` / `process_activity` / `detection_finding` 後續補完(實測 OK)。如未來新增 event_class 422,請通知 BP admin 加 mapping。

## SA Login(契約 §3.2)

```
POST /beakplatform/api/open_defense/sa/login
Content-Type: application/json
{"sa_id": "sa_executor_secvm_01_<redacted>", "sa_secret": "..."}

→ 200 OK
{"access_token": "<JWT>", "expires_in": 900, "token_type": "Bearer"}
```

- JWT 有效 15 分鐘
- 限速 **per IP**:10/min(共用同一出口 IP 的多台機器會互吃)
- TokenManager 應該在 token 失效前 60s 主動 refresh(實作見 `od-bridge/od_bridge/executor.py`)

JWT claims(decode 來看):
```
{
  "sub": "<sa_id>",
  "sa_sc": "<service account secure_code>",
  "org": "<org_secure_code>",
  "eps": ["crowdsec","nftables",...],
  "iat": ..., "exp": ...,
  "iss": "beakplatform-open-defense"
}
```

## Decisions API(契約 §5)

### GET 拉決策

```
GET /beakplatform/api/open_defense/decisions?status=pending&limit=100
Authorization: Bearer <jwt>
```

可選 query:
- `status`: `pending`(預設)/ `applied` / `expired` / `failed`
- `enforcement_point`: 只取 `enforcement_points` 含此值的決策
- `limit`: 預設 100,上限 500
- `since`: ISO-8601,增量輪詢

> ⚠️ **回應的決策物件 NOT 包含** `application_result` 或 `error_message` 欄位 —— 那只在 PATCH 寫入時用。要看詳細執行結果得查 BP 端 DB 或 UI(API 列表為精簡輸出)。

### PATCH 回報

```
PATCH /beakplatform/api/open_defense/decisions/<secure_code>
Authorization: Bearer <jwt>
{
  "status": "picked_up|applied|partial|failed",
  "applied_by": "od-bridge@sec-vm",
  "application_result": {...},
  "error_message": "(僅 failed 必填)"
}
```

**狀態轉換規則**(executor 必須遵守):
- `pending → picked_up | applied | partial | failed`
- `picked_up → applied | partial | failed`
- 其他轉換 → 409
- `expired` / `revoked` → 403(只有 BP cron 能寫,executor 嚴禁)

## TTL 自動 unblock(契約 §6.4)

BP 端每分鐘整點 cron 掃 `applied + expires_at < now()`:
- 把原 block 決策改 `expired`
- 寫一筆新的 `unblock` 決策(同 target、同 EPs、`status=pending`)
- executor 拉到後做撤除

⚠️ **executor 不可自行判斷過期就撤** —— 必須等 BP 下對應 unblock。
⚠️ host kernel TTL 與 BP TTL 之間有時差(我們 nftables enforcer 會用 `timeout Ns`,可能比 BP cron 早 expire)。enforcer 收到 unblock 時若 set 已空,回 `note: already_absent`,**仍然 PATCH applied** 而非 failed。

## decided_via 欄位

允許值:**只有** `human` / `auto` / `ai`。寫 `system` 等其他值會撞 DB CHECK 約束 → BP 會自動轉 `auto`、把原請求字串塞 `decision_metadata.requested_via`。executor 不應對此欄位做行為判斷。

## enforcement_points 字串

「自由字串」,但建議用契約 §6.3 標準清單:

```
crowdsec / nftables / iptables / cloudflare / fastly / aws_waf / edl /
app_internal / siem_tag / email_relay
```

bridge 對 `MY_ENFORCEMENT_POINTS` 之外的 EP **silently skip**(不 PATCH)。如果一筆決策含多個 EP,bridge 只執行交集那些。

## allowed_source_systems

每把 intake key 限定可宣稱的 `source_system`,實測組合:
```
coraza, suricata, falco, crowdsec, vector
```

⚠️ ModSecurity 我們本來想用 `modsecurity` 標籤,**不在清單裡 → 403**。實測改成 `coraza`(同類 WAF 引擎)即通過。

## 已知 BP 端 bug 與修復

| Bug | 觀察 | 修復狀態 |
|---|---|---|
| `fw_workflow_instances.execution_code` 唯一鍵 race | 6 並發 intake 時其中幾筆 500 UniqueViolation | ✅ 已修(advisory lock per org+date) |
| `/decisions` 端點漏 SA-JWT decorator | login 200 + GET 401 | ✅ 已修(後重啟 dev server 即生效) |
| Flask debug=off 不 auto-reload | 加新檔案要手動重啟 | ⚠️ ops note,非 bug |

## 已知 limit / 設計取捨

- BP **不主動發 outbound webhook**;executor 永遠 pull(契約 §1)
- 一個 case 對應一個 form_instance + workflow_instance,目前所有 event_class 走同一個「弱點追蹤」表單模板(可後續拆分)
- 決策 GET API 不回 `application_result` / `error_message`(列表精簡;要詳查走 BP UI 或 DB)
- BP DB CHECK 約束可能限制某些自由字串(`decided_via` 僅三選一)
- `OD-YYYYMMDD-NNNN` 編號格式由 BP 維護,不要在 bridge 端解析或假設順序

## 申請流程(契約 §10)

向 BP admin 提出:
- 事件來源系統清單(對應 `source_system` 值)
- 預計事件量級
- 執行端類型(對應 `enforcement_points` 值)

BP admin 在 BP 端建 Intake Key + Service Account,**密鑰透過安全管道一次性傳遞**。

## 反向(BP → bridge)的最小聯絡

BP 不主動連 bridge,但你可以在 BP UI 觀察 bridge 工作狀況:
- decision 從 `pending` → `picked_up` → `applied` 的時間差(< 5 秒視為健康)
- 連續 `failed` 表示 enforcer 出問題(看 `application_result` JSON)
- 長時間 `pending` 表示 executor 沒拉(查 sec-vm `od-bridge` 容器是否 alive、SA login 是否被 429 卡住)
