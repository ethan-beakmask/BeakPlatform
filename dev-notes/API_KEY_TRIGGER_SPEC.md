# 平台級 API Key 管理與外部發動表單 -- 規格

> 建立日期：2026-07-08
> 狀態：已確認（用戶拍板：統一 HMAC、分階段收斂、修 B-1）
> 相關：`dev-notes/knowledge/auto-form-trigger.md`、`dev-notes/integrations/quick_form_submit_api.md`、`dev-notes/integrations/open_defense_contract.md`

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
| P2 | open_defense 的 OdIntakeKey 遷移至平台 ApiKey（一次性 migration，intake 改讀平台 key） | 已完成（2026-07-08） |
| P3 | 流程節點「API Key 處置」（`ApiKeyAction`：suspend/resume，供資安流程機器處置疑似盜用） | 已完成（2026-07-08） |

## 一、資料模型：`api_keys`（平台層）

`backend/app/models/api_key.py`，migration `scripts/migrations/legacy/077_api_keys.sql`。

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
  "form_template": ["<FwFormTemplate SC>", "..."], // 推薦：穩定且精確，自助申請使用
  "form_category": ["<FwCategory SC>", "..."],   // 表單分類授權（父分類自動含子分類）
  "form": ["<published SC>", "..."]              // 例外：直綁個別表單（選用）
}
```

表單發動 scope 由 form_workflow 模組解釋：

| scope key | 綁定目標 | 取捨 |
|---|---|---|
| `scopes.form_template` | `fw_form_templates.secure_code` | 推薦；穩定且精確，自助申請使用 |
| `scopes.form_category` | `fw_categories.secure_code` | 穩定，但會涵蓋該分類日後新增的表單；父分類自動含子分類 |
| `scopes.form` | `fw_published_form_workflows.secure_code` | published SC 直綁，重新發行後失效；僅一次性測試用 |

未來 P2 的 OD scope 如 `{"od_intake": {...}}` 同構擴充。

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
  "form_code": "HR_ACCOUNT_CREATE",
  "published_secure_code": "...",
  "subject": "人資系統 - 建立帳號申請",
  "form_data": {"field_key": "value"}
}
```

表單識別方式：

- 推薦使用 `form_code`（`fw_form_templates.code`）：同一企業內跨重新發行版本穩定，平台會解析成該表單最新的 `Published` 快照。
- `published_secure_code` 保留相容既有整合，但它會隨表單重新發行而失效，只適合一次性測試；長期對接請用 `form_code`。
- `published_secure_code` 與 `form_code` 擇一必填；兩者都給時以 `published_secure_code` 為準。
- 兩者都未提供或皆為空值時回 400 `missing_form_identifier`。

`form_code` 路徑的錯誤語意（2026-08-27 PF-159 驗收後定版）：

| 情況 | 回應 |
|---|---|
| 該企業沒有這個 code | 404 `form_not_found` |
| code 存在但不在這把 key 的 scope 內 | 404 `form_not_found`（**不洩漏存在與否**） |
| 在 scope 內、從未發行 | 422 `form_not_published` + 「表單尚未發行」 |
| 在 scope 內、有發行記錄但已下架 | 422 `form_not_published` + 「目前沒有 Published 版本」 |

**未發行時無法用 published 判 scope，改判 template SC 或 template 的
`category_secure_code`**（`_template_in_scope()`）。少了這一道，任何持有本企業 key
的人都能用 422 與 404 的差異列舉出企業內所有表單 code——驗收時實測確認過這條路徑存在並已修補。

**`fw_form_templates.code` 不是唯一鍵**（`idx_fw_form_templates_code` 是非唯一索引，
實測 `SEC_INCIDENT_RESPONSE` 在兩個企業各一筆），所有以 code 查詢的地方
一律同時帶 `org_secure_code`，且 org 只能取自 `g.api_key_org`。

處理順序：

1. `@api_key_hmac_required`（含限流，見第五節）
2. **scope 授權**：published 表單的來源 form_template SC ∈ `scopes.form_template`、
   來源 form_template 分類 ∈ `scopes.form_category`（含父分類展開），或
   published SC ∈ `scopes.form`。既有 `published_secure_code`
   路徑失敗時維持 403 `scope_denied`；`form_code` 路徑失敗時回 404
   `form_not_found`，避免洩漏同企業中不在 scope 內的表單存在性。
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
- P2：~~OdIntakeKey 遷移平台 ApiKey~~ **已完成（2026-07-08）**：
  - migration `079_migrate_od_intake_keys.py`：secret 密文五欄位直搬、key_id 沿用
    `ik_` 前綴（新發一律 `ak_`）、`allowed_source_systems` 收進
    `scopes.od_intake.source_systems`、停用 key 轉 `suspended`
  - `@webhook_hmac_required` 改讀平台 ApiKey，雙軌收頭 `X-BP-*`（優先）與
    `X-OD-*`（deprecated），驗證核心與 `@api_key_hmac_required` 共用
    （`_verify_platform_api_key`，含 allowed_ips 檢查）
  - intake 端點加 `od_intake` scope 檢查（無 scope 403 `scope_denied`）
  - OD 管理端 `/open-defense/intake-keys` 唯讀化（create/revoke 回 410）後，
    已於 2026-08-17 透過 migration `105_drop_od_intake_keys.py` 移除
    `od_intake_keys` 表
  - 平台 `/security/api-keys/` UI 支援 od_intake scope（來源系統清單編輯、
    摘要顯示、未知 scope key 編輯時原樣保留）
  - E2E 10/10 PASS（舊頭/新頭/原生 key 收單、source 403、scope 403、
    錯簽章 401、暫停 401、冪等 duplicate、od key 打表單閘道遭拒）
- P3：~~`api_key_action` 流程節點~~ **已完成（2026-07-08）**：
  - node type `ApiKeyAction`（分類「安全」，migration `080_seed_api_key_action_node.sql`
    走 DB 定義，FRONT-03；`require_system_admin=false`，handler 強制租戶隔離）
  - handler `api_key_action_handler.py`：action suspend/resume、
    key 來源三種（trigger=發動本流程的 key / static=指定 key / variable=變數解析）、
    暫停原因支援變數替換、冪等（已是目標狀態視為成功）、
    僅本企業未撤銷 key 可處置
  - 設計器面板 `wf-node-api-key-action.js`（指定 key 清單來自
    `GET /api/workflows/data/org-api-keys`，不含 secret）
  - Handler 單元測試 10/10 PASS（含跨租戶、冪等、變數替換、錯誤路徑）
  - 順手修復三項既有問題：
    1. `wf-node-alert-broadcast.js` 角色/部門清單 fetch 前綴錯誤
       （`/api/form-workflow/data/` → `/api/workflows/data/`，原本 404 被 catch 吃掉）
    2. `workflow_node_definitions.icon` 殘留舊部署前綴 `/bp/static/`（23 筆），
       palette 圖示全部 404 破圖。DB 正規化為 `/static/...`，
       API `get_node_definitions()` 回傳時以 `request.script_root` 補前綴
    3. node-definitions 的 category_map 缺「安全」分類，DecisionWriter/ApiKeyAction
       原會落入「基本節點」。後端補 `'安全': 'security'`，
       前端 palette 補「安全管控」分類（排在系統專用之前）
- 突發保護 B/C（`dev-notes/handoff_burst_protection_ABC.md`）：executor 並發封頂、事件聚合
