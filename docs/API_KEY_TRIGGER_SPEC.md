# 平台級 API Key 管理與外部發動表單 -- 規格

> 建立日期：2026-07-08
> 狀態：已確認（用戶拍板：統一 HMAC、分階段收斂、修 B-1）
> 相關：`docs/knowledge/auto-form-trigger.md`、`docs/integrations/quick_form_submit_api.md`、`docs/integrations/open_defense_contract.md`

## 背景與目標

一般表單先誕生，資安表單因「多外部系統、大量、獨立體系、廠商協同」需求 clone 而生，
造成資安路徑（HMAC webhook）反而比一般路徑成熟。本規格收斂為**一套平台級 API Key 體系**：

- 企業級 API Key 管理（`/security/api-keys`），每個外部系統一把專屬 key，來源清楚
- 一般表單獲得與資安表單同級的外部發動能力（HMAC 簽章閘道）
- 願景鏈：條件觸發開單記錄 → 流程元件深度判斷 → 機器處置或升級人工 → 完整流程記錄
  （取代 log + 小程式 + 排程的舊手法）
- SaaS 多租戶：防護以 **key 暫停**為主，不做平台級 IP 封鎖（避免企業互鎖；
  OS 層封鎖由 BeakMeshWall 負責）

## 階段規劃

| 階段 | 內容 | 狀態 |
|------|------|------|
| P1 | 平台 ApiKey 模型/服務 + `/security/api-keys` UI + 一般表單外部發動閘道 + B-1 限流修復 | 本次實作 |
| P2 | open_defense 的 OdIntakeKey 遷移至平台 ApiKey（一次性 migration，intake 改讀平台 key） | 待排 |
| P3 | 流程節點「API Key 處置」（`api_key_action`：suspend/resume，供資安流程機器處置疑似盜用） | 待排 |

## 一、資料模型：`api_keys`（平台層）

`backend/app/models/api_key.py`，migration `scripts/migrations/077_api_keys.sql`。

| 欄位 | 型別 | 說明 |
|------|------|------|
| （BaseModel 標準欄位） | | id / secure_code / is_deleted / created_at ... |
| `org_secure_code` | String(32) idx | 租戶隔離（TENANT-01） |
| `key_id` | String(40) unique | 公開識別碼，`ak_` + 8 hex |
| `name` | String(200) | key 名稱 |
| `consumer_label` | String(200) | 使用者/裝置標籤（如「台北機房 FW-01」） |
| `description` | String(500) | 說明 |
| `secret_ciphertext` 等 5 欄 | | HMAC secret，沿用 KeyManager Org Key AES-256-GCM 加密五欄位模式（同 OdIntakeKey） |
| `status` | String(20) | `active` / `suspended` / `revoked`（暫停可復原、撤銷不可） |
| `suspended_reason` | String(500) | 暫停原因（人工或未來 P3 節點寫入） |
| `suspended_at` | DateTime | |
| `allowed_ips` | JSONB nullable | 每把 key 選配的來源 IP 白名單（CIDR 支援）；NULL = 不鎖（動態 IP 場景） |
| `scopes` | JSONB | 授權範圍，見下 |
| `applicant_user_secure_code` | String(32) nullable | 綁定的專用系統帳號，發動之表單以此為申請人；NULL 則申請人僅記 consumer_label |
| `expires_at` | DateTime nullable | 使用期限，NULL = 永久 |
| `last_used_at` | DateTime | |
| `created_by_secure_code` | String(32) | 建立者 |

**secret 一次性顯示**：建立時回傳 base64 明文一次，之後僅能重建（revoke + 新建），不能重看。

### scopes 格式（平台不解釋語意，由各消費端解釋自己的 scope type）

```json
{
  "form_category": ["<FwCategory SC>", "..."],   // 表單分類授權（父分類自動含子分類）
  "form": ["<published SC>", "..."]              // 例外：直綁個別表單（選用）
}
```

採分類授權為主（用戶決策：東方企業表單浮濫，一對一綁定難管理），
個別表單直綁保留為例外用法。未來 P2 的 OD scope 如 `{"od_intake": {...}}` 同構擴充。

## 二、認證：HMAC 簽章（統一，不做 bearer）

沿用 open_defense 已驗證的簽章規格（`modules/open_defense/services/hmac_verifier.py` 純函式直接複用）：

```
canonical = "{timestamp}\n{原始 body bytes}"
X-BP-Key-Id:     ak_xxxxxxxx
X-BP-Timestamp:  Unix 秒（±300s 容忍）
X-BP-Signature:  sha256=<hex(HMAC-SHA256(secret, canonical))>
```

平台層新增 decorator `@api_key_hmac_required`（`backend/app/security/decorators.py`）：

1. headers 齊備 → 2. timestamp 容忍內 → 3. key_id 查 active 未過期 ApiKey
→ 4. `allowed_ips` 檢查（有設定才檢） → 5. 解密 secret、`hmac.compare_digest` 驗章
→ 成功注入 `g.api_key`，touch `last_used_at`。
失敗一律 401 `auth_failed`（不區分原因，避免探測），記 log 供 BeakMeshWall 取用。

## 三、外部發動閘道（form_workflow 模組）

`modules/form_workflow/api/external_trigger.py`：

### `POST /api/trigger/form`

```json
{
  "published_secure_code": "...",
  "subject": "人資系統 - 建立帳號申請",
  "form_data": {"field_key": "value"}
}
```

處理順序：

1. `@api_key_hmac_required`（含限流，見第五節）
2. **scope 授權**：published 表單的來源 form_template 分類 ∈ `scopes.form_category`
   （含父分類展開）或 published SC ∈ `scopes.form`，否則 403 `scope_denied`
3. 租戶隔離：published 必須屬 key 的 `org_secure_code`
4. **form_data schema 白名單驗證**：key 必須存在於 form schema `components[]`
   中 `input: true` 的欄位（遞迴展開容器元件），出現未知 key → 400 `unknown_field`
5. 申請人：key 綁定的系統帳號（須 `is_active` 且未刪，DATA-01）；未綁定則
   `applicant_secure_code=None`、`applicant_name=consumer_label`
6. 建立 FwFormInstance（`source_type='API_KEY'`、`source_api_key=key_id`、`source_ip` 記錄）
   + 啟動 workflow（同 fc_fill 正式模式邏輯，序號走 NumberingService）
7. 回 201：`form_instance_secure_code` / `serial_number` / `execution_code`

不支援測試模式（同 OD webhook 原則）。

### `GET /api/trigger/forms`

回傳該 key scope 內可發動的 published 表單清單（SC、名稱、欄位 schema 摘要），
供外部整合者對接時查詢，同樣走 HMAC 認證。

## 四、管理 UI：`/security/api-keys`

- 位置：安全中心（`backend/app/web/security_center.py` + `backend/app/api/security_center.py` 或獨立 api 檔）
- 權限：`@admin_required`（企業管理員管自己企業的 key）
- 功能：列表（key_id、名稱、使用者標籤、狀態、期限、最後使用）、建立（secret 只顯示一次）、
  暫停/復原（填原因）、撤銷、編輯（名稱/說明/IP 白名單/scope/期限；secret 不可改）
- scope 選擇器：分類樹（呼叫 form_workflow 既有分類 API）+ 個別表單搜尋
- 選單：`menu_items` 新增（MENU-01：`link_type='url'`，`link_target='/security/api-keys/'`，
  掛在安全中心父選單下，參照同層現有記錄）
- 前端遵循 FRONT-01/02：JS 抽 `api-keys.js`，模板 < 500 行

## 五、B-1 修復：限流繞過

問題：`key_func_from_intake_key` 以未驗證的 header key_id 當限流 bucket，
假 key_id 輪替可取得無限額度。

修法（新舊端點一併）：

- 保留 per-key 業務限流（合法 key 之間互不影響）
- 新增 **per-IP 認證失敗限流**：`@limiter.limit('30 per minute', key_func=get_remote_address,
  deduct_when=response.status_code == 401)` — 只對 401 扣次，正常流量不受影響
- 適用：`/api/open_defense/intake`、`/api/trigger/form`、`/api/trigger/forms`

註：此為應用層第一道；持續攻擊源交由 BeakMeshWall 從 OS 層封鎖。

## 六、安全對照（SECURITY_PITFALLS 檢核）

- 租戶隔離：ApiKey 全查詢帶 `org_secure_code`；閘道驗 published 歸屬
- 帳號狀態：綁定申請人時檢查 `is_deleted=False AND is_active=True`
- secure_code：URL/API 一律用 SC，無自增 ID
- 密鑰：secret 加密存放、不落 log、不可重看；HMAC 驗證 timing-safe
- 選單：只動 DB `menu_items`，不碰 `_resolve_link()` 與權限核心

## 七、遺留追蹤（不在本次範圍）

- A-1：~~`/api/form-center/submit` 正式模式未驗 `FwMappingPermission`~~
  **已修（2026-07-08）**：權限解析抽為共用 `services/fill_permission_service.py`，
  `fc_available`（列表可見性）與 `fc_fill` submit（送單）使用同一套判斷；
  無權限送單回 403。E2E 驗證：授權用戶 201、未授權用戶 403、ORG_ADMIN
  無授權記錄時同樣 403（與列表可見性一致，ORG_ADMIN 非硬編碼放行角色）。
- P2：OdIntakeKey 遷移平台 ApiKey
- P3：`api_key_action` 流程節點（workflow_node_definitions 新 node type + handler，FRONT-03 走 DB 定義）
- 突發保護 B/C（`docs/handoff_burst_protection_ABC.md`）：executor 並發封頂、事件聚合
