# OpenDefense 模組架構（平台側）

**最後更新：2026-08-10**
**權威範圍**：本檔只寫 `/opt/BeakPlatform-dev` 內的實作。
平台外的組件（`.20` 上的 Vector / Suricata / Coraza / CrowdSec / od-bridge /
EDL enforcer / ClickHouse）**不在本檔範圍**，那些的權威文件在
`/opt/Ethan_Lab/ITHome-2026/CLAUDE.md`；跨主機拓樸與運維手法也在那邊。

**為什麼要分**：兩邊各自會改，複製一份必定漂移。
2026-07-16 之後 open_defense 的程式碼一路改到 08-10，而 `docs/` 停在 07-16，
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
| 對外契約 | `docs/integrations/open_defense_contract.md` v1.0，**已凍結** | 無契約，設定驅動 |
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

詳情區是三個分頁（2026-08-10 起）：

| 分頁 | 內容 | 何時出現 |
|---|---|---|
| 案件摘要 | 軸線六格、簽核歷程、1-click 處置、關聯決策 | 一律 |
| 事件明細 | `form_data` 裡的明細陣列渲染成表格，欄位標籤取自 `profile.detail_columns`，沒設定就用原欄位名 | 有明細列時 |
| 原始欄位 | 扁平化的原始欄位（排除軸線、`od_` 開頭、明細陣列本身） | 有欄位時 |

OCSF 案件沒有 profile 也沒有明細陣列，只會看到兩個分頁——這是預期。
明細列裡的時間是**來源系統的原樣字串**（格式不保證），刻意不做時區換算。
- SLA：severity ≥4 為 15 分鐘、=3 為 60 分鐘，低危無 SLA。
  起點是 `submitted_at`（naive UTC，前端計算前要補 `Z`）
- 簽核授權走 `modules/form_workflow/services/task_authorizer.py`
  （快照 ∪ 當前角色 ∪ 生效中代理），**判定點共 12 處，不要另外寫**

`form_data` 的欄位在 list 與 detail 語境都會過出口政策
（EGRESS-01，資源代碼 `fw_form:<模板SC>`）。

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
- `docs/integrations/open_defense_contract_v2_draft.md` 與
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
| 檔案清單（改哪些檔） | `docs/manifests/mod-open-defense.yaml` |
| OCSF 對外契約 v1.0 | `docs/integrations/open_defense_contract.md` |
| SOC 角色分工設計 | `docs/guides/SOC_ROLE_DESIGN_GUIDE.md` |
| 平台外組件（.20 的 Vector/Suricata/CrowdSec/od-bridge/EDL） | `/opt/Ethan_Lab/ITHome-2026/CLAUDE.md` |
| 跨 session 決策脈絡 | BeakBroodNest 知識庫（`note_search("open-defense")`） |
