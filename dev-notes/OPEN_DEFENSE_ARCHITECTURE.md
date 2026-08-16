# OpenDefense 模組架構（平台側）

**最後更新：2026-08-15**
**權威範圍**：本檔只寫 `/opt/BeakPlatform-dev` 內的實作。
平台外的組件（`.20` 上的 Vector / Suricata / Coraza / CrowdSec / od-bridge /
EDL enforcer / ClickHouse）**不在本檔範圍**，那些的權威文件是
`dev-notes/SEC_STACK_ARCHITECTURE.md`；跨主機拓樸與運維手法也在那邊
（PF-104 起收斂，取代原本外部路徑 `/opt/Ethan_Lab/ITHome-2026/CLAUDE.md`；
該外部副本**已於 2026-08-15 刪除**，備份見 `SEC_STACK_ARCHITECTURE.md` 開頭）。

**為什麼要分**：兩邊各自會改，複製一份必定漂移。
2026-07-16 之後 open_defense 的程式碼一路改到 08-10，而 `dev-notes/` 停在 07-16，
就是因為沒有一個「平台側該寫哪、外部該寫哪」的分界。

## 1. 這個模組在做什麼

外部安全設備偵測到事件 → 推進 BeakPlatform → 依規則決定用哪張表單/流程 →
建成案件走簽核 → 簽核結果寫成「防禦決策」→ 外部執行端拉走並落地實施。

```
外部偵測端 ──HMAC webhook──> intake ──路由規則──> form_workflow 案件
                                                      │ 簽核（處置中心 1-click）
                                                      ▼
                                            DecisionWriter 節點
                                                      │
                                            od_defense_decisions
                                                      │ SA JWT 拉取
                                                      ▼
                                              外部執行端（封鎖/解封）
```

模組**完全共用 form_workflow 引擎**，沒有自己的表單或流程實作。
處置中心的簽核動作直接打 `/api/form-center/pending-tasks` 的 lock/approve。

## 2. 事件進入平台的兩條路徑

| | OCSF 路徑 | 原生 payload 路徑 |
|---|---|---|
| 端點 | `POST /api/open_defense/intake` | `POST /api/open_defense/intake/native?profile=<code>` |
| 格式 | 自訂 OCSF-ish schema，欄位固定 | **任意 JSON**，由 payload profile 描述怎麼解析 |
| schema 驗證 | `schemas/intake.py::validate_intake_body()` | 只驗「是 dict」與大小上限 256KB |
| 對外契約 | `dev-notes/integrations/open_defense_contract.md` v1.0，**已凍結** | 無契約，設定驅動 |
| 冪等鍵 | body 的 `correlation_id` | `profile.correlation_id_path` 取值（>64 字元改存 `h:<sha256 前 32>`）|
| 上線 | 2026-07 | 2026-08-10 |

兩條路徑**共用**：HMAC 認證、限流、冪等表、路由、聚合降噪、enrichment、建案。

### 認證與限流（兩條相同）

- `@webhook_hmac_required`：header `X-BP-Key-Id` / `X-BP-Timestamp` /
  `X-BP-Signature`（`sha256=hex(HMAC-SHA256(secret, "{ts}\n{body}"))`），
  timestamp ±300 秒。舊的 `X-OD-*` 仍相容但已 deprecated
- key 是平台 ApiKey（`api_keys` 表，**狀態欄位是 `status`不是 `is_active`**），
  必須具備 `scopes.od_intake`
- `scopes.od_intake.source_systems`：允許的來源系統白名單，不在清單一律 403
- `scopes.od_intake.payload_profiles`（可選，僅 native 路徑）：允許使用的
  profile code 白名單。**沒有這個鍵時不限制**（向下相容既有 key）
- 限流：`100 per minute; 5000 per hour`，key_func 以 key_id 計數，
  另疊認證失敗限流

### 端對端送一筆測試事件（本機實測可用，2026-08-16 驗過）

三個一定會撞的點，先看這裡可省一輪試誤：

1. **端點是 `/api/open_defense/intake`**，沒有 `/events` 這一層
2. **契約必填五個頂層欄位**：`correlation_id` / `source_system` / `event_class`
   （限 `detection_finding` / `network_activity` / `web_activity` / `process_activity`）
   / `occurred_at`（ISO-8601 UTC 字串）/ `severity_id`（int 0~6）。
   缺任一個回 400 `validation_error` 並列出欄位
3. **`source_system` 要在該 key 的白名單內**，否則 403 `source_not_allowed`。
   查法：`SELECT key_id, scopes FROM api_keys WHERE key_id LIKE 'ik_%';`
   （開發庫的 `ik_5ad9de314382ac38` 含 coraza/suricata/falco/crowdsec/vector）

執行前提（三項都要成立，否則錯誤會指向不相干的地方）：

```bash
systemctl is-active beakplatform-dev.service          # 必須是 active
cd /opt/BeakPlatform-dev && set -a && source .env && set +a   # 缺 SECRET_KEY 會 ValueError
./venv/bin/python -c "import requests, psycopg2; print('ok')" # 兩個套件 venv 內已有
# 確認要用的 key 還在、scopes 沒被改
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A \
  -c "SELECT key_id, status, scopes FROM api_keys WHERE key_id LIKE 'ik_%';"
```

腳本存檔後用 `./venv/bin/python <檔案>` 跑（不要用系統 python3，套件不在那裡）。

```python
# 本 session 實跑成功
import hashlib, hmac, json, time, uuid, requests
from datetime import datetime
from app import create_app
from app.models.api_key import ApiKey
from app.services import api_key_service

KEY_ID, NONCE = 'ik_5ad9de314382ac38', uuid.uuid4().hex[:8]
app = create_app('development')
with app.app_context():
    secret = api_key_service.decrypt_secret(ApiKey.query.filter_by(key_id=KEY_ID).first())

payload = {
    'correlation_id': f'probe-{NONCE}', 'source_system': 'falco',
    'event_class': 'network_activity',
    'occurred_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'severity_id': 3,
    'actor': {'ip': '10.99.88.77'},                       # 私有網段：會被保護清單擋，不會真的封鎖
    'target': {'host': f'probe-{NONCE}.example.test'},
    'finding': {'rule_id': f'PROBE-{NONCE}', 'title': f'probe {NONCE}'},
}
body = json.dumps(payload, separators=(',', ':')).encode()   # 簽章與送出必須是同一份 bytes
ts = str(int(time.time()))
sig = hmac.new(secret, f'{ts}\n'.encode() + body, hashlib.sha256).hexdigest()
r = requests.post('http://192.168.0.16:7000/beakplatform/api/open_defense/intake',
                  data=body, headers={'Content-Type': 'application/json',
                  'X-BP-Key-Id': KEY_ID, 'X-BP-Timestamp': ts,
                  'X-BP-Signature': f'sha256={sig}'}, timeout=30)
print(r.status_code, r.text)
```

成功時的回應（頂層四個鍵，`duplicate=true` 代表 `correlation_id` 撞冪等表、沒有建新案）：

```json
{"case_secure_code":"2R6iw_yX60pyz6wZMc3OuQ","duplicate":false,"success":true,"workflow_started":true}
```

**HTTP 200 只代表事件收下了，要確認案件真的建起來就查 DB**（用回應的
`case_secure_code`，或用自己送的 `correlation_id` 反查）：

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -F'|' -c "
SELECT e.correlation_id, wi.execution_code, wi.status, fi.serial_number
FROM od_intake_events e
JOIN fw_workflow_instances wi ON wi.secure_code = e.case_secure_code
JOIN fw_form_instances fi     ON fi.secure_code = wi.form_instance_secure_code
WHERE e.correlation_id = 'probe-<你的 NONCE>';"
```

查無資料而 HTTP 是 200 → 多半是被聚合降噪併進既有案件（見下段），
不是建案失敗；`case_secure_code` 會指向那張既有案件。

聚合降噪會把「同 `finding.rule_id` + 同 `actor.ip` + 同 `target.host`」併進既有案件，
所以三個鍵都要帶 nonce，否則拿到的是上一輪的案件與節點軌跡。

### 原生路徑的解析流程

```
?profile=<code> ──> OdPayloadProfile（帶 org 過濾、is_active）
     │
     ├─ correlation_id_path ──> 冪等鍵 ──> 重複就直接回 duplicate
     ├─ field_map ──────────> 共同軸線 6 欄
     ├─ kv_expansions ──────> Extensions[] 這種 KV 陣列攤成 Extensions.<name>
     ├─ detail_path/item_key > 明細陣列（EventContents[].Content）
     └─ 其餘 ────────────────> 整包扁平化成 Summary.RuleId 這種 key
```

唯一實作是 `services/payload_profile_service.py`，
**任何地方要對事件 JSON 取值或攤平，一律呼叫它**（`routing_service` 的條件比對
也是用它的 `get_path()`）。

防爆上限：巢狀深度 6、扁平 key 500 個、單一字串 8000 字元、明細 500 列。
超過只截斷並記 warning，不讓整包事件失敗。

## 3. 共同軸線：兩種格式的交會點

處置中心要跨案件排序、算 SLA、統計，所以**不論哪種來源格式，
intake 都會把這 6 個 key 正規化後寫進 `form_data`**：

```
severity_id  actor_ip  target_host  source_system  finding_rule_id  occurred_at
```

OCSF 路徑由 `intake_service._build_form_data()` 直接映射；
原生路徑由 `payload_profile_service.normalize_axis_fields()` 依 `field_map` 映射。

**這組 key 是相容性契約**：SLA（`security_cases._sla_minutes` 讀 `severity_id`）、
聚合降噪（`actor_ip` + `finding_rule_id`）、風險分數、處置中心清單全部讀它。
改名等於同時弄壞四個機制。

系統另外維護的欄位：`od_event_count`、`od_first_seen`、`od_last_seen`、
`od_repeat_count`、`od_history_block_count`、`risk_score`、`recommended_action`、
`od_payload_profile`（只有原生案件有，值是 profile code）。

## 4. 規則式路由（決定用哪張表單 = 決定這是哪類案件）

表：`od_form_template_mappings`。唯一實作：`services/routing_service.py`。

一條規則就是一個**案件類型**。多條規則可以指向同一張表單（多對一），
所以「內對內橫向掃描」與「內對內暴力破解」可以共用一套處理流程，
也可以各自走不同流程——差別只在規則指向哪張表單。

| 欄位 | 說明 |
|---|---|
| `priority` | **大的先比對，第一個命中就採用**（不是分數加總） |
| `payload_kind` | `ocsf` / `native` / NULL（不限）。避免包底規則跨格式誤命中 |
| `event_class` | 只有 OCSF 用，可空；空值代表不比對這個維度 |
| `match_rules` | 條件陣列，**全部成立才命中**（AND） |
| `form_template_secure_code` | 目標表單模板 |
| `is_active` | |

條件格式：`{"field": "Summary.RuleId", "op": "startswith", "value": "AV-"}`

`field` 是點號路徑，直接對事件原始 JSON 取值——OCSF 寫 `finding.rule_id`，
原生 SOC 通報寫 `Summary.RuleId`。運算子只有 12 個：
`eq` `ne` `in` `not_in` `gt` `gte` `lt` `lte` `contains` `startswith` `endswith` `exists`。
**沒有 regex，是刻意排除的（ReDoS）。**

無命中一律 422 `no_mapping`（fail-closed，不會塞給預設表單）。

**規則式路由不回溯既有案件**：改規則只影響之後進來的事件，
已建立的案件表單歸屬永遠不變。

### 管理頁 `/open-defense/event-routing`（2026-08-10 起）

兩個分頁：**路由規則**（CRUD、優先序、條件編輯器）與**來源格式**
（payload profile 的 CRUD、軸線映射、嚴重度對照、明細欄位標籤、KV 展開）。
兩邊各有一個**試算**區：貼一包真實事件 JSON，
規則側顯示命中哪一條與被哪個條件擋下，格式側顯示解析出的冪等鍵、
軸線 6 欄、明細筆數與 `form_data` 預覽。**試算不寫任何資料。**

頁面與 API 都鎖 `open_defense.admin`（D2：按鈕包 `BkCaps.can()`，
API 掛 `@permission_required`）。在此之前這兩張表只能用 API 或直接改 DB 維護。

## 5. 案件建立與聚合降噪

`intake_service` 拿到 `form_template_secure_code` 之後：

1. 找該表單**最新的 Published 快照**（`fw_published_form_workflows`，
   `status='Published'` 依 `published_at` 倒序取第一筆）。
   沒有已發行版本 → 422 `form_not_published`
2. 建 `fw_form_instances` + `fw_workflow_instances` + 起始節點 queue item
3. 流水號 `OD-YYYYMMDD-<8 hex>`（`serial_number`），
   流程編號 `OD-YYYYMMDD-NNNN`（`execution_code`，**UI 上顯示的是這個**）

**聚合降噪**：同 `actor_ip` + `finding_rule_id`、60 分鐘窗內的事件併進既有案件，
不開新案——`od_event_count` 累加、severity 取 max、風險分數重算。
兩個鍵**任一為空就不聚合**（原生 SOC 通報常常沒有來源 IP，
此時每包事件各自開案才是對的）。

**比對依據一律是案件表單的共同軸線，不是 `raw_body`**（PF-75，2026-08-10 修）。
`_find_mergeable_case()` 走三層 join
（`od_intake_events` → `fw_workflow_instances` → `fw_form_instances`）
比對 `form_data->>'actor_ip'` 與 `form_data->>'finding_rule_id'`。

**不要改回讀 `raw_body`。** 原本寫死 v1 OCSF 的巢狀路徑
（`raw_body['actor']['ip']`、`raw_body['finding']['rule_id']`），
而原生 payload 的 `raw_body` 是來源系統的原始結構（`Summary.RuleId` 這類），
兩個路徑恆為 NULL——**原生路徑的聚合因此 100% 失效且完全無聲**
（呼叫端有正確算出軸線值並傳入，失效發生在候選池那一層）。
`form_data` 的 6 個共同軸線才是兩種格式的交會點（見 §3）。

**格式隔離**：原生事件只與同 `source_system` 的原生事件合併；
OCSF 只與 OCSF 合併。跨格式軸線碰巧相同時不再互相誤合。
`payload_kind` 非 `ocsf`/`native`、或原生缺 `source_system` 時
一律 fail-closed 回 None（寧可多開一張案，不可合進錯的案）。

**同一個坑在 `_enrich_form_data()` 也踩過**（同批修）：
`od_repeat_count`（24 小時內同 IP 事件數）原本同樣讀 `raw_body['actor']['ip']`，
對原生案件恆為 0 → `_compute_risk()` 低估 → `recommended_action` 偏向 observe。
現已改為同樣的 join + `form_data` 比對。
此處**刻意不做格式隔離**：同一 IP 被不同偵測器看到正是風險升高的訊號。

## 6. 資安案件處置中心 `/open-defense/security-cases`

SOC 值班介面。案件的判定是**表單分類前綴** `CAT_SECURITY_`
（常數在 `modules/form_workflow/services/security_center.py`），
一般表單中心已排除此前綴，兩邊不會互相看到。

- 清單 API `/api/open_defense/cases`（**不在 `/admin` 底下**）：讀共同軸線那組 key
- 統計 `/api/open_defense/cases/stats`
- 明細 `/api/open_defense/cases/<wi_sc>/payload`：原始欄位與事件明細表格
- 決策關聯 `/api/open_defense/cases/<wi_sc>/decisions`
- **跨系統關聯 `/api/open_defense/cases/<wi_sc>/cross-source`（PF-106，2026-08-15 起）**：
  即時查 `.20` 的 ClickHouse（`secstack.events`），找同 `actor_ip` 在
  `submitted_at~completed_at ± 24h` 時間窗內、各資安套件各自記錄的事件。
  承接 PF-100 的問題分析——平台把同一攻擊者的多系統告警拆成各自獨立的案件，
  這支端點把它們重新串起來（唯讀查詢，不改變既有聚合/建案邏輯）。

詳情區是動態分頁（2026-08-15 起，PF-106 在原本三個固定分頁之外，
依 ClickHouse 查詢結果動態附加）：

| 分頁 | 內容 | 何時出現 |
|---|---|---|
| 案件摘要 | 軸線六格、`first_detected_by`/`last_detected_by`（見下）、簽核歷程、1-click 處置、關聯決策 | 一律 |
| 事件明細 | `form_data` 裡的明細陣列渲染成表格，欄位標籤取自 `profile.detail_columns`，沒設定就用原欄位名 | 有明細列時 |
| 原始欄位 | 扁平化的原始欄位（排除軸線、`od_` 開頭、明細陣列本身） | 有欄位時 |
| **跨系統關聯** | 時間窗內各系統的事件時間軸、相異來源數、各系統的 rule 與標題 | ClickHouse 查得到 ≥1 筆關聯事件時 |
| **各套件（Coraza/WAF、Suricata、...）** | 該來源在時間窗內的原始事件列表（時間、嚴重度、規則、標題、目標、UA） | 每個實際出現的 `source_system` 各一頁，動態產生 |

OCSF 案件沒有 profile 也沒有明細陣列，只會看到兩個分頁——這是預期。
明細列裡的時間是**來源系統的原樣字串**（格式不保證），刻意不做時區換算。
- SLA：severity ≥4 為 15 分鐘、=3 為 60 分鐘，低危無 SLA。
  起點是 `submitted_at`（naive UTC，前端計算前要補 `Z`）
- 簽核授權走 `modules/form_workflow/services/task_authorizer.py`
  （快照 ∪ 當前角色 ∪ 生效中代理），**判定點共 12 處，不要另外寫**

`form_data` 的欄位在 list 與 detail 語境都會過出口政策
（EGRESS-01，資源代碼 `fw_form:<模板SC>`）。跨系統關聯回傳的
`target_host` / `actor_xff` 沿用同一套政策（同資源代碼、`detail` 語境）。

### 6.1 跨系統關聯查詢（PF-106）

唯一實作：`modules/open_defense/services/cross_source_service.py`
（查詢邏輯）+ `modules/open_defense/services/clickhouse_client.py`
（低階 HTTP 客戶端，唯一允許呼叫 ClickHouse 的地方）。

- **租戶隔離**：ClickHouse `secstack.events` 沒有 `org_secure_code`。
  `case_cross_source()` 一律先用 `_security_case_query(org.secure_code)`
  驗過案件屬於當前企業，才把驗證過的 `actor_ip` 交給
  `cross_source_service.get_cross_source()`——**沒有任何路徑能繞過這層驗證
  直接查 ClickHouse**。查無案件（不屬本企業或不存在）一律 404，
  與既有 `payload`/`decisions` 端點一致
- **認證**：header `X-ClickHouse-User` / `X-ClickHouse-Key`（`clickhouse_client.py`
  唯一實作），設定在平台 `.env` 的 `CLICKHOUSE_URL` / `CLICKHOUSE_DB` /
  `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD`（`backend/app/config.py`）。
  **禁止**改用 `?user=&password=` 或 `requests.get(..., auth=(...))`
  （後者一樣是明文 HTTP Basic Auth，會觸發 Suricata 告警，PF-106 已踩過）
- **SQL 注入防護**：查詢一律用 ClickHouse 參數化語法 `{name:Type}` +
  query string `param_<name>`（含資料庫名，用 `{db:Identifier}`），
  由伺服器端做型別化替換，**不是字串拼接**
- **時間窗**：`submitted_at ~ completed_at`（進行中案件用現在時間頂替
  `completed_at`）前後各加 24 小時，常數
  `security_cases.py::CROSS_SOURCE_WINDOW_PAD`
- **資料可信度**：`RELIABLE_FROM = 2026-08-08`（見本檔 §「重要修正」段落與
  PF-106 工單同名段落）。查詢時間窗若跨過此日期，回應會帶
  `window_crosses_backfill_boundary: true`，前端顯示提醒，
  **不宣稱該期間筆數代表真實全量**
- **first_detected_by / last_detected_by**：分開用一個 `GROUP BY source_system`
  聚合查詢算（不是從明細列表取頭尾，避免明細被 `MAX_EVENTS=300` 截斷時
  算錯 last_detected_by）
- **ClickHouse 不可用**（未設定/連線失敗/逾時）時，`clickhouse_client.query()`
  回 `None`，`cross_source_service` 據此回
  `{'available': False, 'reason': 'clickhouse_unavailable'}`，
  API 仍回 **HTTP 200**——前端因此隱藏「跨系統關聯」與各套件分頁，
  不讓案件頁整頁失敗。2026-08-15 已實測停用 `secstack-clickhouse-1`
  容器驗證此行為（見 `/opt/tmp/verify/20260815-pf106-crosssource.log`）
- **PF-100 範例 IP `203.0.113.77` 查證結果**：該範例是從平台
  `od_intake_events` 交叉查詢得出的，其中 `soc_splunk` 來源與部分
  `suricata`（`rule_id` 如 `100002`/`9999999`/`VERIFY-*`）事件是**直接打
  native intake API 灌入的測試資料**（PF-75 驗證探針），從未經過 `.20` 的
  Vector/Suricata 真實管線，ClickHouse 端查不到。**驗證這支功能請改用
  `198.51.100.201`**（PF-103 go-ftw 樣本，coraza+suricata 皆為真實流量，
  見下方驗收記錄）

## 7. 防禦決策與執行端

- 表：`od_defense_decisions`。由流程中的 **DecisionWriter 節點**寫入
  （handler 在 `modules/form_workflow/services/node_handlers/`）
- 外部執行端以 Service Account JWT 拉取：
  `POST /api/open_defense/sa/login` → `GET /api/open_defense/decisions`
  → `PATCH /api/open_defense/decisions/<sc>` 回報
- **狀態流轉受限**：執行端只能寫 `picked_up` / `applied` / `partial` / `failed`；
  `expired` / `revoked` 由平台排程獨佔

## 8. 排程（`/etc/crontab`）

| 腳本 | 做什麼 |
|---|---|
| `scripts/cron/od_expire_decisions.py` | 掃過期的 applied 決策 → 自動產生 unblock |
| `scripts/cron/od_canary_check.py` | 確認 `.20` 每小時打的 canary 有變成案件，沒有就發 Telegram |

兩支都支援 `--dry-run`，正常完成會寫 heartbeat。

## 9. 資料表一覽

| 表 | 用途 |
|---|---|
| `od_intake_events` | 收到的事件原始記錄（`raw_body` JSONB 完整保留），冪等鍵 + 稽核線索 |
| `od_form_template_mappings` | 規則式路由（＝案件類型） |
| `od_payload_profiles` | 原生 payload 的來源格式設定檔 |
| `od_defense_decisions` | 防禦決策（執行端拉取的對象） |
| `od_service_accounts` | 執行端帳號 |
| `od_intake_keys` | **唯讀遺留**，已遷移到平台 `api_keys`，保留一個版本週期 |

全部有 RLS（`org_secure_code = current_setting('app.current_org', true)`）。

**`od_intake_events.case_secure_code` 指向 `fw_workflow_instances`，不是
form_instance。**要拿到表單得再 join 一層：

```sql
FROM od_intake_events e
JOIN fw_workflow_instances wi ON wi.secure_code = e.case_secure_code
JOIN fw_form_instances fi     ON fi.secure_code = wi.form_instance_secure_code
```

## 10. 排錯

| 症狀 | 先查什麼 |
|---|---|
| intake 回 422 `no_mapping` | 路由規則沒命中。用 `POST /api/open_defense/admin/routing-rules/test` 貼同一包 JSON 試算，看是哪個條件擋下的 |
| intake 回 422 `form_not_published` | 表單模板沒有 Published 快照，或改了模板沒重新發行 |
| 改了流程 graph 卻沒生效 | publish 以 version+revision 判斷有無變更。直接改 `fw_workflow_templates.graph` 不會 bump revision，要先 `UPDATE ... SET revision = revision+1` 再 publish |
| 原生案件的表單欄位全空 | profile 的 `field_map` / 扁平化 key 與表單欄位 key 對不上。用 `/payload-profiles/<sc>/test` 看實際產出的 key |
| 案件建了但處置中心看不到 | 表單模板的分類不是 `CAT_SECURITY_` 前綴 |
| 權限判定失敗 | 一律回 404 不洩漏存在與否；原因看 `sudo journalctl -u beakplatform-dev.service --since "-5 min" \| grep reason=` |

## 11. 未竟事項

- **舊案件不回溯**：7760 張舊 OD 案件用「弱點追蹤」表單、無 `CAT_SECURITY_` 分類，
  不會出現在處置中心，規則式路由也不會改變它們的歸屬（BBN atom #5110、PF-73）
- **`?profile=` 不在 HMAC 簽章範圍內**：簽章只涵蓋 timestamp 與 body。
  持有效 key 者可自行更換 profile（受 `scopes.od_intake.payload_profiles` 白名單約束）
- 封鎖時長仍是 DecisionWriter 節點上的常數（BBN atom #5114 有決策庫構想）
- ~~原生路徑聚合降噪失效~~ → **PF-75，2026-08-10 已修**（見 §5）。
  同批修掉 `_enrich_form_data()` 的 `od_repeat_count` 同源缺陷
- `dev-notes/integrations/open_defense_contract_v2_draft.md` 與
  `raw_store_and_archive_spec.md` 的**決策點已於 2026-08-10 全部拍板**
  （v2 契約 §0.6、raw store §8），狀態改為「規格定案、待實作」。
  已定的六件事：聚合下推 `.20` 且視窗 60 分鐘、`dedup_key` 不納入 target、
  locator 路徑 `raw_events/<date>/<incident_id>`、反向通道走 `.20` 的
  nginx + Flask、只先做查原文（§3）規則回饋（§4）延後、冷層過渡到
  `.16` 的 `/mnt/smb/soc_archive/`。**實作主體在 `.20`**，
  平台側只有兩件：Phase 2c 停用 v2 envelope 的合併、Phase 3b 案件詳情頁「查原文」按鈕

## 12. 相關文件

| 找什麼 | 去哪 |
|---|---|
| 檔案清單（改哪些檔） | `dev-notes/manifests/mod-open-defense.yaml` |
| OCSF 對外契約 v1.0 | `dev-notes/integrations/open_defense_contract.md` |
| SOC 角色分工設計 | `docs/guides/SOC_ROLE_DESIGN_GUIDE.md` |
| 平台外組件（.20 的 Vector/Suricata/CrowdSec/od-bridge/EDL） | `dev-notes/SEC_STACK_ARCHITECTURE.md` |
| .20 上的設定檔權威副本（版控） | 頂層 `sec-vm-bootstrap/`（PF-104 起，不會推 GitHub） |
| 跨 session 決策脈絡 | BeakBroodNest 知識庫（`note_search("open-defense")`） |
