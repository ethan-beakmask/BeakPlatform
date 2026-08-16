## 安全規範（BeakPlatform 是多租戶權限平台，這些不是建議）

### 租戶隔離

- 所有查詢必須含 `org_secure_code` 過濾；PostgreSQL RLS 是最後防線
- **org 值只能來自登入身分**（`current_user.org_secure_code`）、API key
  （`g.api_key.org_secure_code`）或 service account。**禁止從 request body 或
  query string 取 org**——那是越權，這是租戶隔離最重要的一條
- ResourceGateway 依範圍而定，**不是一律強制**：
  - **新寫的平台 API（`backend/app/api/`）一律走 `ResourceGateway`**，
    不要因為「隔壁既有的也沒走」就跟著寫 `Model.query`
  - 平台 API 且 model 已註冊 `MODEL_RESOURCE_TYPE_MAP` → **必須**走 `ResourceGateway`
  - 模組 API（`modules/*/api/`）→ **沿用該檔既有寫法**（目前是 `Model.query`
    ＋顯式 org 過濾）。模組 model 沒有註冊進 gateway，改走 gateway 會被
    fail-closed 拒絕而 403/500。**不要順手把模組 API 改成 ResourceGateway**
- **禁止修改 `MODEL_RESOURCE_TYPE_MAP`、`LIST_RBAC_ENFORCED_MODELS`、
  `RBAC_EXEMPT_MODELS`**（`backend/app/security/resource_gateway.py`）。
  這三張表全平台生效，改它們不是改一支 API。**model 沒註冊就維持 `Model.query`
  現狀**，不要為了「讓它能走 gateway」而去註冊——註冊了卻沒建 permission code 時，
  `PermissionService.check()` 會在查不到定義那一步直接 return False，
  **連 ORG_ADMIN 與 SYSTEM_ADMIN 都被擋**（bypass 在下一步、輪不到），
  症狀是整個端點對每種身分都 403
- 改既有平台 API 為 gateway 時（**只在 spec 明確要求時做**）：
  `ResourceGateway.list()` / `filter()` 會對 `LIST_RBAC_ENFORCED_MODELS` 內的 model
  自動檢查 `{resource_type}:read`，**不是等價替換**——EMPLOYEE／EXTERNAL 可達的端點
  改完會 403。呼叫端本來就不該持有該權限時用 `check_permission=False` 並寫明理由。
  **這件事單元測試抓不到**（測試庫沒有 RBAC seed），要在回報中列為需人工實測項
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

### 公開端點必須評估 rate limit

**新增任何不需登入即可呼叫的端點（`@public_route`、portal `/public/...`、
webhook、匿名送件），都必須在交付回報中明確說明有沒有掛 rate limit 與理由。**
沒評估等於漏掉——匿名端點沒有帳號可以鎖，rate limit 是唯一的節流手段。

掛法（`limiter` 從 `app` 匯入，裝飾器疊在路由下方）：

```python
from app import limiter

@bp.route('/public/xxx', methods=['POST'])
@limiter.limit('10 per minute; 100 per hour')
def xxx():
    ...
```

- 寫入型匿名端點（送件、留言）參考既有 portal 的
  `10 per minute; 100 per hour`（`modules/nocode_builder/web/portal_public.py`）
- 帶 API Key 的機器端點用 `key_func` 以 key 而非 IP 計數，並額外疊
  `@limiter.limit(**auth_failure_limit_kwargs())` 限制認證失敗次數
  （範例：`modules/form_workflow/api/external_trigger.py`）
- 限額若需讓管理者可調，走 `RateLimitService.get_limit('<category>')`
  的 lambda 形式，不要寫死字串
- 純讀取且結果可公開的端點可以不掛，但**必須在回報中說出這個判斷**

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
