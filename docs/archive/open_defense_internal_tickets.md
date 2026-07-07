# Open Defense 模組 — 內部實作工單

**對外契約**: `docs/integrations/open_defense_contract.md` v1.0(凍結)
**Manifest**: `docs/manifests/mod-open-defense.yaml`
**最後更新**: 2026-05-09

---

## 全模組共通遵守(每張 ticket 都適用)

| 規範 | 來源 | 重點 |
|---|---|---|
| TENANT-01 | CLAUDE.md | 所有表 RLS,所有查詢過濾 `org_secure_code` |
| TENANT-02 | CLAUDE.md | API 一律經 `ResourceGateway`,禁 `Model.query` |
| AUTH-01/02 | CLAUDE.md | 嚴格用既有 decorator;新增 decorator 走 `security/decorators.py` |
| DATA-01 | CLAUDE.md | 查 user 必過濾 `is_deleted=False` + `is_active=True` |
| SECURE-CODE | CLAUDE.md | PK 一律 `secure_code`(`generate_secure_code()`),禁 auto-id 對外 |
| TZ-01 | CLAUDE.md | UTC 入庫,模板用 `\|tz_format`,JS 用 `BkTime.format()` |
| FRONT-01/02/05/07 | CLAUDE.md | JS/CSS 抽離靜態檔,模組 CSS 用 `od-` 前綴,**無** Bootstrap |
| FRONT-03 | CLAUDE.md | 新 node type 必須登錄 `workflow_node_definitions` DB 表 |
| Manifest | CLAUDE.md | 修改前查 manifest,完成後驗證 `mod-open-defense.yaml` 一致性 |

**安全核心檔案修改**(`security_core_touch` 列出者):每次都要在 commit message 標註並等用戶確認。

---

## 交付順序與相依

```
TICKET-1 (DB 模型 + migration)
    │
    ├─► TICKET-2 (HMAC 簽章驗證 + decorator,屬安全核心擴充)
    │       │
    │       └─► TICKET-3 (Webhook intake API)
    │
    ├─► TICKET-5 (Service Account + JWT decorator,屬安全核心擴充)
    │       │
    │       └─► TICKET-6 (決策只讀 / 回報 API)
    │
    └─► TICKET-4 (DecisionWriter workflow node handler)

(平行,UI 不擋執行端開發)
TICKET-7 (UI:dashboard / decisions / intake-keys / service-accounts)
TICKET-8 (排程:過期決策自動產生 unblock,15 分鐘 cron)
```

每張 ticket 完成後:`git add -A && git commit`,**不主動 push**(等用戶下令)。

---

## TICKET-1:資料模型 + migration

### 目標檔案

| 路徑 | 內容 |
|---|---|
| `modules/open_defense/__init__.py` | 模組 metadata |
| `modules/open_defense/models/__init__.py` | 匯出 4 個模型 |
| `modules/open_defense/models/intake_key.py` | `OdIntakeKey` |
| `modules/open_defense/models/intake_event.py` | `OdIntakeEvent` |
| `modules/open_defense/models/defense_decision.py` | `OdDefenseDecision` |
| `modules/open_defense/models/service_account.py` | `OdServiceAccount` |
| `scripts/migrations/<TS>_create_open_defense.sql` | DDL + RLS policy + index |

### Schema 要點

**`od_intake_keys`**

| 欄位 | 型別 | 備註 |
|---|---|---|
| `secure_code` | varchar(40) PK | 內部識別 |
| `org_secure_code` | varchar(40) NOT NULL | 租戶 |
| `key_id` | varchar(40) UNIQUE | 對外公開,如 `ik_a3f9c2e1` |
| `name` | varchar(200) | 人類可讀名稱 |
| `hmac_secret_encrypted` | bytea | 用 Org Key 加密的 32-byte secret |
| `hmac_secret_nonce` | bytea | AES-GCM nonce |
| `allowed_source_systems` | jsonb | 允許的 `source_system` 字串清單 |
| `is_active` | boolean DEFAULT true | |
| `expires_at` | timestamp | NULL 表永不過期 |
| `last_used_at` | timestamp | 統計用 |
| `created_by_secure_code` | varchar(40) | |
| `created_at` / `updated_at` / `is_deleted` | 標準 |

**`od_intake_events`**(冪等 + 稽核)

| 欄位 | 型別 | 備註 |
|---|---|---|
| `secure_code` | varchar(40) PK | |
| `org_secure_code` | varchar(40) NOT NULL | |
| `correlation_id` | varchar(64) NOT NULL | 對外冪等鍵,**全表 UNIQUE** |
| `intake_key_secure_code` | varchar(40) | 來源 key |
| `source_system` | varchar(50) | |
| `event_class` | varchar(30) | |
| `severity_id` | smallint | |
| `raw_body` | jsonb | 原始 OCSF body |
| `signature_verified` | boolean | |
| `case_secure_code` | varchar(40) | 對應 form_instance |
| `received_at` | timestamp NOT NULL | |
| `created_at` / `is_deleted` | 標準 |

**`od_defense_decisions`** — 詳見契約 §1.2,但對內補充:

- 加 `intake_event_secure_code`(來源事件)欄位以利溯源。
- 加 `revoked_by_decision_secure_code`(若被後續 unblock 撤銷,指向那筆 unblock 決策)。

**`od_service_accounts`**

| 欄位 | 型別 | 備註 |
|---|---|---|
| `secure_code` | varchar(40) PK | |
| `org_secure_code` | varchar(40) NOT NULL | |
| `sa_id` | varchar(60) UNIQUE | 對外,如 `sa_executor_crowdsec_01` |
| `name` | varchar(200) | |
| `secret_hash` | varchar(255) | bcrypt(secret),不存明文也不可解密 |
| `allowed_enforcement_points` | jsonb | 此 SA 允許拉取的 EP,空陣列=全部 |
| `is_active` | boolean | |
| `last_login_at` | timestamp | |
| `last_login_ip` | inet | |
| `created_by_secure_code` | varchar(40) | |
| `created_at` / `updated_at` / `is_deleted` | 標準 |

**金鑰處理對比**:
- intake_key 的 HMAC secret 需要**驗章時還原**,故對稱加密儲存(沿用 `crypto/key_manager` Org Key)。
- service_account 的 secret 只用於登入比對,故 bcrypt **單向雜湊**,密鑰建立時一次性顯示後不可還原。
- 兩者**不可共用儲存策略**。

### RLS Policy(每張表)

```sql
ALTER TABLE od_xxx ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_od_xxx_tenant ON od_xxx
  USING (org_secure_code = current_setting('app.current_org', true));
```

### 必要 Index

```sql
CREATE UNIQUE INDEX uq_od_intake_correlation ON od_intake_events(correlation_id);
CREATE INDEX idx_od_decisions_pending  ON od_defense_decisions(status, expires_at)
  WHERE status='pending';
CREATE INDEX idx_od_decisions_target   ON od_defense_decisions(target_type, target_value);
CREATE INDEX idx_od_decisions_org_time ON od_defense_decisions(org_secure_code, created_at DESC);
CREATE INDEX idx_od_decisions_ep      ON od_defense_decisions USING gin (enforcement_points);
CREATE INDEX idx_od_keys_keyid         ON od_intake_keys(key_id) WHERE is_deleted=false;
CREATE INDEX idx_od_sa_said            ON od_service_accounts(sa_id) WHERE is_deleted=false;
```

### 驗收

- [ ] migration 可在 dev DB 反覆執行不出錯(支援 idempotent 或附 rollback)
- [ ] RLS policy 啟用,以未設 `app.current_org` 的 session 查表回 0 列
- [ ] 模型透過 `db.create_all()` 也能建出相同 schema(防 ORM 與 SQL 漂移)

---

## TICKET-2:HMAC Webhook 驗證機制(安全核心擴充)

> **此 ticket 觸碰 `backend/app/security/`,屬安全核心,實作前需向用戶報備並二次確認。**

### 目標

新增 `@webhook_hmac_required` decorator,支援:
1. 從 `X-OD-Key-Id` 取得 key,反查 `od_intake_keys`
2. 驗證 `X-OD-Timestamp` 在 ±300 秒內
3. 驗證 `X-OD-Signature` = `sha256(timestamp\nbody)`
4. 將解密後的 key record 注入 `g.intake_key`,後續 view 可用

### 目標檔案

| 路徑 | 動作 |
|---|---|
| `backend/app/security/decorators.py` | 新增 `webhook_hmac_required(key_loader)` |
| `backend/app/security/auth_interceptor.py` | 白名單加入 `/api/open_defense/intake`(僅該路徑放行,內部仍由 decorator 驗 HMAC) |
| `backend/app/security/rate_limiter.py` | 新增 `key_func_from_intake_key()`、`key_func_from_sa_id()` 兩個 helper |
| `modules/open_defense/services/hmac_verifier.py` | 純函式,輸入 (timestamp, body, secret),輸出 bool |

### 實作規範

- decorator 內**先驗時間戳再驗簽章**,避免無效時間戳浪費 HMAC 計算
- 所有 4xx 回應 body 統一格式 `{"error": "<code>"}`,`<code>` 對應契約 §4.4
- decorator **禁** log 簽章內容或 secret,僅 log `key_id` + 結果(verified/failed)
- HMAC 驗證使用 `hmac.compare_digest`(timing attack 防護)

### 限速整合

- intake 路由套 `@limiter.limit("100 per minute; 5000 per hour", key_func=key_func_from_intake_key)`
- key_func 先嘗試取 `X-OD-Key-Id`,缺值 fallback `get_remote_address`(防 anon flood)

### 驗收

- [ ] 缺 header → 401
- [ ] 時間戳偏差 > 300s → 401
- [ ] 簽章錯 → 401(且 log 顯示 `key_id` 但不顯示簽章)
- [ ] 簽章對 → view 取得 `g.intake_key.org_secure_code`
- [ ] 重發同一請求(同 timestamp + body)在 5 分鐘內**仍可成功**(冪等由 correlation_id 處理,不是時間戳;此處只防 5 分鐘外的 replay)

---

## TICKET-3:Webhook Intake API + 流程啟動

### 目標檔案

| 路徑 | 內容 |
|---|---|
| `modules/open_defense/api/intake.py` | `POST /api/open_defense/intake` view |
| `modules/open_defense/services/intake_service.py` | 接收事件 → 寫 event → 啟 workflow |
| `modules/open_defense/schemas/intake.py` | marshmallow / pydantic schema 驗證 |

### 實作邏輯

```
1. @webhook_hmac_required 通過 → g.intake_key 可用
2. schema 驗證 body (契約 §4.3)
3. 檢查 source_system 在 g.intake_key.allowed_source_systems
4. 用 correlation_id 查 od_intake_events:
   - 存在 → 200 {"duplicate": true, "case_secure_code": existing.case_secure_code}
5. 不存在 → 寫 od_intake_events,signature_verified=true
6. 依 event_class 對應到「處置單」表單模板:
   - mapping 來自 od_intake_keys.default_form_template_code(可選)
   - 或硬編 default(detection_finding → "od_default_finding"),這個對應表寫在 service 層常數
7. 透過 form_workflow 的 instance service 啟動 workflow,
   把 OCSF 欄位注入 form 的初始 values
8. 回寫 od_intake_events.case_secure_code
9. 回 200 {"case_secure_code": "...", "workflow_started": true}
```

### 不能踩的雷

- **禁** 直接 `Model.query`,所有寫入經 `ResourceGateway`(TENANT-02)
- **禁** 把 raw_body 整段寫進 form initial values(可能含 PII / 過大),只取必要欄位映射到 form field
- **禁** 在 webhook 內做重 IO(如查 IP threat intel),這類補強應放到 workflow 第一個 node 處理

### 驗收

- [ ] 正確 body + 簽章 → 200,DB 多一筆 event + 一個 form_instance
- [ ] 重送同 correlation_id → 200 + duplicate=true,**不重複建 event 或 instance**
- [ ] source_system 不在白名單 → 403
- [ ] body 缺欄位 → 400 + details
- [ ] 高負載測試:1000 並發同一 correlation_id,最終 DB 只有 1 筆 event(用 unique index 保證)

---

## TICKET-4:DecisionWriter Workflow Node Handler

### 目標檔案

| 路徑 | 動作 |
|---|---|
| `modules/form_workflow/services/node_handlers/decision_writer_handler.py` | 新建 handler |
| `modules/form_workflow/services/node_handlers/factory.py` | 註冊 `decision_writer` |
| migration 內 seed | `workflow_node_definitions` 加一筆 `decision_writer` |

### Handler 邏輯(參考 `alert_broadcast_handler.py` 結構)

```python
class DecisionWriterHandler(BaseNodeHandler):
    def handle(self):
        self.report_running()
        action = self.get_config_value('action')                  # block/unblock/...
        target_type = self.get_config_value('target_type')
        target_value = self.replace_variables(
            self.get_config_value('target_value'))                 # 從 form 欄位讀
        enforcement_points = self.get_config_value(
            'enforcement_points', [])
        ttl = self.get_config_value('ttl_seconds')
        reason = self.replace_variables(
            self.get_config_value('reason_template', ''))

        # 必填檢查 + 值域檢查
        if action not in VALID_ACTIONS: return error(...)
        if target_type not in VALID_TARGET_TYPES: return error(...)

        from modules.open_defense.services.decision_service import (
            create_decision)

        decision = create_decision(
            org_secure_code=self.queue_item.org_secure_code,
            case_secure_code=self.queue_item.workflow_instance_secure_code,
            workflow_node_id=self.node_id,
            action=action,
            target_type=target_type,
            target_value=target_value,
            enforcement_points=enforcement_points,
            ttl_seconds=ttl,
            reason=reason,
            decided_via=self._infer_decided_via(),  # human/auto/ai
            decided_by_secure_code=self._infer_decider(),
            related_intake_event_sc=self._lookup_source_event(),
        )
        return {'status': 'success',
                'data': {'decision_secure_code': decision.secure_code}}
```

### Node 配置欄位(workflow-designer UI)

| 欄位 | 型別 | 變數替換 |
|---|---|---|
| `action` | enum | 是 |
| `target_type` | enum | 否 |
| `target_value` | string | **是**(通常 `${form.actor_ip}`) |
| `enforcement_points` | multi-select | 否 |
| `severity` | enum | 是 |
| `ttl_seconds` | int / null | 否 |
| `reason_template` | textarea | 是 |

### 驗收

- [ ] 在 workflow-designer 可拖出 `decision_writer` 節點並設定
- [ ] 流程跑到該節點 → DB 多一筆 `od_defense_decisions`,`org_secure_code` 正確繼承
- [ ] 變數替換失敗(如 `${form.xxx}` 不存在)→ 節點回 error,不阻塞流程
- [ ] **跨租戶測試**:模擬不同 org 的 instance,decision.org_secure_code **絕對**等於 form_instance.org_secure_code

---

## TICKET-5:Service Account + JWT(安全核心擴充)

> **此 ticket 觸碰 `backend/app/security/`,需用戶確認。**

### 目標檔案

| 路徑 | 內容 |
|---|---|
| `backend/app/security/decorators.py` | 新增 `@service_account_required` |
| `backend/app/security/auth_interceptor.py` | 白名單加入 `/api/open_defense/sa/login` |
| `modules/open_defense/services/service_account_service.py` | bcrypt 驗 secret + 簽 JWT |
| `modules/open_defense/api/service_accounts.py` | `POST /api/open_defense/sa/login` |

### JWT 規格

- 演算法 HS256
- 簽章 secret 從 `app.crypto` 取(專用於 SA JWT,**不**與檔案加密 master key 共用)
- claims:`{sub: sa_id, org: org_secure_code, eps: [...], iat, exp}`
- exp 預設 15 分鐘(可由 `OD_SA_JWT_TTL_SEC` 環境變數覆寫)
- decorator 驗 JWT → 將 SA 資訊注入 `g.service_account`

### login 端點限速

- `@limiter.limit("10 per minute", key_func=get_remote_address)`(防憑證爆破,沿用 IP 軸是合理的)
- 連續失敗(同 sa_id)5 次 → 帳號鎖定 15 分鐘(寫 `od_service_accounts.lock_until`)

### 驗收

- [ ] sa_id + secret 對 → 200 + JWT
- [ ] secret 錯 5 次 → 帳號鎖
- [ ] 過期 JWT → 401
- [ ] 缺 Authorization header → 401

---

## TICKET-6:決策只讀 / 回報 API

### 目標檔案

| 路徑 | 內容 |
|---|---|
| `modules/open_defense/api/decisions.py` | `GET` / `PATCH` 端點 |
| `modules/open_defense/services/decision_service.py` | 業務邏輯 |

### 端點

```
GET  /api/open_defense/decisions  (見契約 §5.1)
PATCH /api/open_defense/decisions/<sc>  (見契約 §5.2)
```

### 規範

- `@service_account_required` 套用
- limiter:GET `60/min, 3000/hour, 50000/day`,PATCH `300/min`,key_func 用 `sa_id`
- GET 結果**只回該 SA 的 org**(從 JWT claim 取),且**只回 `enforcement_points` 與 SA 的 `allowed_enforcement_points` 有交集**的決策
- PATCH 狀態轉換驗證(契約 §5.2 表),禁止寫 `expired` / `revoked`
- 樂觀鎖:PATCH `picked_up` 時用 `WHERE status='pending'` 條件,避免雙人搶同一筆

### 驗收

- [ ] SA-A 不能拉到 SA-B 所屬 org 的決策
- [ ] EP 不交集 → 不會出現在結果
- [ ] 兩個 SA 同時 PATCH 同一 pending → 一個成功、一個 409
- [ ] PATCH 試圖寫 `expired` → 403

---

## TICKET-7:UI 與 dashboard

### 頁面

| URL | 用途 | 角色限制 |
|---|---|---|
| `/open-defense/dashboard` | 統計卡(今日新事件 / 待執行 / 已執行 / 失敗 / 平均處理時間) | org admin |
| `/open-defense/decisions` | 決策列表(篩 status / EP / 時間 / 撤銷按鈕) | org admin |
| `/open-defense/intake-keys` | HMAC key CRUD,**新建時一次性顯示 secret** | org admin |
| `/open-defense/service-accounts` | SA CRUD,**新建時一次性顯示 sa_secret** | org admin |

### 前端規範

- 每個 HTML ≤ 500 行(FRONT-02),超過抽 partial / static js
- JS 用模式 B(window bridge)為主
- CSS 用 `od-` 前綴,**不**用 Bootstrap class(FRONT-07)
- datetime 一律 `BkTime.format()` / `|tz_format`(TZ-01)

### 驗收

- [ ] 4 個頁面正常顯示資料,排序預設依 `created_at desc`
- [ ] 一次性 secret 顯示後重新整理頁面**不再顯示**
- [ ] 撤銷按鈕觸發後,decision 加一筆對應 unblock(同 target,action='unblock')

---

## TICKET-8:過期決策排程(產生 unblock)

### 目標檔案

| 路徑 | 內容 |
|---|---|
| `modules/open_defense/services/expiry_service.py` | 掃 expired,產生 unblock decision |
| `scripts/cron/od_expire_decisions.py` | 入口 script,寫 heartbeat |
| `/etc/crontab` | 註冊,每分鐘跑(本機開發環境用 systemd timer 也可) |

### 邏輯

```
SELECT * FROM od_defense_decisions
WHERE status='applied'
  AND ttl_seconds IS NOT NULL
  AND expires_at < now()
  AND id NOT IN (SELECT revoked_by_decision_secure_code WHERE not null)

對每筆:
  1. 建立同 target、action='unblock'、enforcement_points 同的新 decision(status='pending')
  2. 原 decision.status='expired',revoked_by_decision_secure_code=新 decision.sc
  3. commit per row(避免長交易)
```

### 規範

- heartbeat 寫 `/opt/tmp/heartbeat/od_expire_decisions`(全域 CLAUDE.md heartbeat 規範)
- log 寫 `/opt/tmp/BeakPlatform-dev-cron-od_expire_decisions.log`
- script 必須支援 `--dry-run` 參數
- 失敗(DB 連不上)時 retry 3 次後告警,**不**自動修補資料

### 驗收

- [ ] 手動把一筆 decision 的 expires_at 設為過去 → 下次 cron 跑後產生對應 unblock
- [ ] dry-run 模式不寫 DB,僅印行為
- [ ] heartbeat 檔在每次成功跑完更新 mtime

---

## 開工前必須與用戶確認的決策點

1. **金鑰加密**:HMAC secret 用 `crypto/key_manager` 的 Org Key 加密儲存 — 是否同意沿用?如果這是「平台級」的設施(跨 org 共用),用 Master Key 也許更乾淨。
2. **Form template default mapping**:`event_class → form_template_code` 的預設對應寫在哪?service 常數 / DB 表 / 設定頁?
3. **decision_writer 節點權限**:這個節點寫的決策會直接被外部執行端拉走實施,屬高敏感操作。是否在 workflow-designer 限制只有 system_admin 角色能放置此節點?
4. **TICKET-2 / TICKET-5 觸碰安全核心**:每張 PR 都需單獨確認,還是現在一次授權整個模組的安全核心修改?
5. **migration 編號**:目前 `scripts/migrations/` 用什麼編號慣例?(看現有檔再決定,但若有規則請告知)

---

## 開工順序建議

我建議**先完成 TICKET-1 與 TICKET-4**(DB + node handler),這兩張不觸碰安全核心,可以快速跑出端對端流程(用 fixture 模擬 webhook 入庫,看到 decision 寫出),先驗證資料流通暢。

之後再做 TICKET-2/3/5/6 的對外暴露面。

確認以上 5 點後,我從 TICKET-1 開始實作。
