## 安全規範（BeakPlatform 是多租戶權限平台，這些不是建議）

### 租戶隔離

- 所有查詢必須含 `org_secure_code` 過濾；PostgreSQL RLS 是最後防線
- **API 層禁止直接用 `Model.query`**，必須透過 `ResourceGateway`
- 看到非預期的 404，先查 `org_secure_code` 再懷疑邏輯（多半是租戶隔離擋掉）

### 帳號查詢（DATA-01）

所有查詢用戶/帳號的地方，必須**同時**過濾 `is_deleted=False` 與 `is_active=True`。
包含用戶列表、組織樹、簽核人選擇、角色成員解析、部門成員解析。
關聯查詢（透過角色/部門取用戶）需 JOIN User 表確認帳號狀態。

### 認證資訊

密碼、API Key、Token **絕對不可硬編碼**，無例外。
`ENCRYPTION_MASTER_KEY` 之類的密鑰不可寫入版控。

### fail-closed 原則

任何不確定的輸入、缺失的設定、未預期的例外，一律**拒絕**，不是放行、不是忽略、
不是回空資料。

「回空資料」特別危險：空資料看起來像「沒有資料」，會讓設定錯誤的功能靜默通過。
必須是明確的拒絕（4xx）。

### SQL 與 DDL

- **禁止**字串拼接 SQL；參數一律走 bind parameter
- 識別字（表名、欄位名）必須先過白名單正則驗證，再用 `_quote()` 包
- 型別、來源這類枚舉值必須比對白名單，不在白名單就 400
- 錯誤訊息**不可包含 SQL 原文或檔案路徑**

### URL 與識別碼

- **禁止**在 URL 使用自增 ID，一律用 `secure_code`

### 元件級權限（D2，PERM-02）

觸及動作按鈕（增刪改查、簽核、撤銷）與動作型 API 的任務：

- 按鈕包 `{% if can('<permission_code>') %}`（JS 用 `BkCaps.can()`）
- 對應動作 API 掛 `@permission_required('<permission_code>')`
  （`from app.services.capability_service import permission_required`）
- permission code 沿用 API 層既有的，不要自創
- 前端檢查只是避免無謂請求，**後端才是防線**，兩者都要有

### 錯誤處理

必須完整，不得「先跑再說」。捕捉例外後要 log（用該檔既有 logger 風格），
不可靜默吞掉。
