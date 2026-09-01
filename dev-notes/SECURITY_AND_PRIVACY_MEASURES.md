# BeakPlatform 資安與隱私措施清單

本文件彙整 BeakPlatform 平台所採用的資訊安全與隱私保護措施，涵蓋架構設計、程式實作、部署組態三個層面。

最後更新: 2026-03-31

---

## 目錄

1. [認證機制](#1-認證機制-authentication)
2. [授權與存取控制](#2-授權與存取控制-authorization--access-control)
3. [多租戶隔離](#3-多租戶隔離-multi-tenant-isolation)
4. [密碼安全](#4-密碼安全-password-security)
5. [會話管理](#5-會話管理-session-management)
6. [速率限制與暴力破解防護](#6-速率限制與暴力破解防護-rate-limiting)
7. [輸入驗證與注入防護](#7-輸入驗證與注入防護-input-validation)
8. [HTTP 安全標頭](#8-http-安全標頭-security-headers)
9. [CSRF 防護](#9-csrf-防護)
10. [資料加密與保護](#10-資料加密與保護-data-protection)
11. [隱私與個資保護](#11-隱私與個資保護-privacy--pii)
12. [稽核日誌](#12-稽核日誌-audit-logging)
13. [部署安全](#13-部署安全-deployment-security)
14. [靜態分析與自動化檢查](#14-靜態分析與自動化檢查-sast)
15. [安全設計原則](#15-安全設計原則-security-by-design)

---

## 1. 認證機制 (Authentication)

### 1.1 全域認證攔截 (AUTH-01: Deny by Default)

| 項目 | 說明 |
|------|------|
| 實作檔案 | `backend/app/security/auth_interceptor.py` |
| 技術 | Flask `before_request` hook，所有請求預設需認證 |
| 白名單機制 | 公開路由以集合 (`PUBLIC_ROUTES_WHITELIST`) + 前綴清單 (`PUBLIC_ROUTE_PREFIXES`) + `@public_route` decorator 三層判斷 |
| 未認證處理 | 非白名單路由一律回傳 401 |
| 帳號狀態驗證 | 認證後額外檢查 `is_active`，停用帳號回傳 403 |

### 1.2 統一認證 Decorator (AUTH-02)

| Decorator | 檢查項目 | 適用場景 |
|-----------|---------|---------|
| `@public_route` | 無認證 | 健康檢查、靜態資源 |
| `@login_required` | 已登入 + is_active | 一般功能頁面 |
| `@admin_required` | 已登入 + (ORG_ADMIN 或 SYSTEM_ADMIN) | 管理功能 |
| `@system_admin_required` | 已登入 + SYSTEM_ADMIN | 系統級管理 |
| `@module_access_required(code)` | 合約驗證 + ACL 檢查 | 模組功能存取 |
| `@permission_required(type, action)` | 資源級 RBAC 權限檢查 | 細粒度操作控制 |

實作檔案: `backend/app/security/decorators.py`

### 1.3 登入流程安全設計

| 措施 | 說明 |
|------|------|
| 統一錯誤訊息 | 帳號不存在與密碼錯誤回傳相同訊息「帳號或密碼錯誤」，防止帳號列舉 |
| Honeypot 欄位 | 共用登入頁內嵌隱藏欄位，偵測自動化攻擊 |
| 禁用「記住我」 | `login_user(user, remember=False)`，關閉瀏覽器即失效 |
| Session 交叉驗證 | `session['_session_org']` 防止 session 被篡改後跨租戶存取 |
| 強制密碼變更 | `must_change_password=True` 時導向密碼變更頁面 |

實作檔案: `backend/app/api/auth.py`

### 1.4 原始管理員初始設定 (AUTH-03)

企業建立後，原始管理員首次登入被強制導向初始設定流程，完成綁定企業管理員帳號後原始管理員即停用。

實作檔案: `backend/app/security/auth_interceptor.py` (行 124-150)

---

## 2. 授權與存取控制 (Authorization / Access Control)

### 2.1 RBAC 角色權限系統

**四層用戶類型（平行結構，非繼承）:**

| 類型 | 說明 | 特權範圍 |
|------|------|---------|
| SYSTEM_ADMIN | 系統管理員 | 跨企業系統管理，但不自動繼承企業權限 |
| ORG_ADMIN | 企業管理員 | 本企業所有非 SYSTEM 級權限 |
| EMPLOYEE | 企業成員 | 依角色指派 |
| EXTERNAL | 外部廠商 | 依角色指派 |

**四層角色層級:**

| 層級 | 適用範圍 |
|------|---------|
| SYSTEM | 系統級 |
| ORG | 企業級 |
| MODULE | 模組級 |
| MEMBER | 成員級 |

實作檔案: `backend/app/models/user.py`, `backend/app/models/role.py`

### 2.2 角色指派與期限控制

- `UserRoleAssignment` 表支援 `valid_from` / `valid_until` 有效期限
- 查詢時自動過濾已過期的指派
- 支援單線繼承 (`inherits_from_secure_code`)，有循環偵測

實作檔案: `backend/app/models/associations.py`, `backend/app/services/permission_service.py`

### 2.3 RBAC + ABAC 混合權限檢查

**PermissionService.check() 流程:**
1. 查詢用戶有效角色（含繼承鏈）
2. 查詢角色持有的權限 (`RolePermission`)
3. 評估 ABAC 條件（`condition_json`）
4. 任一角色通過即放行

**ABAC 條件類型:**

| 類型 | 條件 | 說明 |
|------|------|------|
| 所有權 | OWNER, ASSIGNED | 資源擁有者/被指派者 |
| 組織 | SAME_DEPT, SUB_DEPT, SUBORDINATE | 部門/階層關係 |
| 職等 | MIN_RANK, LOWER_RANK | 職等限制 |
| 時間 | WORK_HOURS, VALID_PERIOD | 時間窗口限制 |
| 狀態 | STATUS_DRAFT, FLOW_PENDING | 資源狀態限制 |

實作檔案: `backend/app/services/permission_service.py`, `backend/app/models/permission_condition.py`

### 2.4 選單雙鑰匙安全模型

| 鑰匙 | 控制項 | 資料來源 |
|------|--------|---------|
| Key1: MenuPermission | 哪種 user_type 可看到選單 | `menu_permissions` 表 |
| Key2: MenuRoleRequirement | 存取選單需要哪些角色 | `menu_role_requirements` 表 |

**判決邏輯:**
- 兩把鑰匙都要通過才能存取
- Key1 過濾可見性，Key2 過濾存取權
- 無角色需求記錄 = 擋下（白名單制）

實作檔案: `backend/app/services/page_role_guard.py`, `backend/app/services/menu_service.py`

### 2.5 頁面角色守衛 (Page Role Guard)

在 `before_request` 階段執行，對所有非 API/靜態路徑的頁面請求進行雙鑰匙檢查。權限不足時強制登出並寫入稽核日誌。

實作檔案: `backend/app/services/page_role_guard.py`

---

## 3. 多租戶隔離 (Multi-Tenant Isolation)

### 3.1 應用層隔離 (TENANT-01)

| 措施 | 說明 |
|------|------|
| org_secure_code 過濾 | 所有租戶資料查詢自動注入 `org_secure_code` 條件 |
| TenantBaseModel | 繼承此 Model 的表自動帶 `org_secure_code` 外鍵 |
| ContextVar 租戶追蹤 | 線程安全的租戶上下文管理 |
| 認證攔截器設定 | `before_request` 階段設定 `g.current_org_secure_code` |

實作檔案: `backend/app/models/base.py`, `backend/app/security/tenant_isolation.py`

### 3.2 ResourceGateway 統一閘道 (TENANT-02)

| 規則 | 說明 |
|------|------|
| API 層禁止 `Model.query` | 所有資料存取必須透過 ResourceGateway |
| 自動租戶過濾 | Model 有 `org_secure_code` 欄位時自動套用 |
| secure_code 格式驗證 | 正則 `^[A-Za-z0-9_-]{10,32}$`，格式不符回傳 404 |
| 保護欄位 | `update()` 禁止修改 `id`, `secure_code`, `org_secure_code`, `created_at` |
| Semgrep 強制 | 自動化規則掃描 API 層是否有直接 Model.query |

實作檔案: `backend/app/security/resource_gateway.py`

### 3.3 PostgreSQL Row Level Security (RLS)

作為「最後防線」的深層防禦，在資料庫層面強制租戶隔離:

- 使用 `current_setting('app.current_org')` 取得當前租戶
- 系統管理員標記 `current_setting('app.is_system_admin')` 可存取所有記錄
- 已啟用 RLS 的表: `lookup_categories`, `lookup_items`, `modules`, `menu_items`, `pages`

實作檔案: `scripts/migrations/legacy/001_menu_system.sql`, `scripts/migrations/legacy/030_lookup_tables.sql`

---

## 4. 密碼安全 (Password Security)

### 4.1 密碼雜湊

| 項目 | 說明 |
|------|------|
| 演算法 | bcrypt (自動 salt) |
| 長度限制 | 72 bytes (bcrypt 上限) |
| 比對方式 | `bcrypt.checkpw()` 時間常數比對，防 timing attack |

實作檔案: `backend/app/models/user.py` (行 174-187)

### 4.2 企業級密碼策略

| 功能 | 說明 |
|------|------|
| 密碼複雜度 | 可配置最低長度、大小寫、數字、特殊字元要求 |
| 密碼歷史 | 儲存舊密碼 hash，防止重複使用 |
| 強制變更 | `must_change_password` 欄位，首次登入或管理員重設後強制變更 |
| 密碼產生器 | 自動產生符合策略的強密碼（12 字元，避免混淆字元） |
| 按企業配置 | 不同企業可設定不同密碼策略 |

實作檔案: `backend/app/services/password_policy_service.py`

### 4.3 帳號鎖定機制

| 項目 | 說明 |
|------|------|
| 觸發條件 | 連續失敗次數達 `max_failed_attempts` |
| 鎖定策略 | 指數退避: `lockout_duration * (multiplier ^ (lockout_times - 1))`，上限 24 小時 |
| 追蹤欄位 | `failed_login_count`, `locked_until`, `last_failed_login` |
| 解鎖 | 登入成功自動重置計數器 |
| 提示 | 剩餘 2 次機會時提示用戶 |

實作檔案: `backend/app/services/password_policy_service.py` (行 286-365)

### 4.4 密碼重設流程（二階段驗證）

1. 用戶申請重設 -> 產生 URL token (32 bytes) + 6 位數驗證碼，10 分鐘過期
2. 驗證信寄至 backup_email，帳號不存在仍回傳成功（防帳號列舉）
3. 用戶輸入驗證碼通過後寄送暫時密碼
4. 暫時密碼登入後強制變更

實作檔案: `backend/app/api/auth.py` (行 828-897), `backend/app/models/password_reset_token.py`

---

## 5. 會話管理 (Session Management)

### 5.1 Cookie 安全設定

| 設定 | Production 值 | 說明 |
|------|-------------|------|
| SESSION_COOKIE_SECURE | True | 僅 HTTPS 傳輸 |
| SESSION_COOKIE_HTTPONLY | True | JavaScript 無法存取 |
| SESSION_COOKIE_SAMESITE | Lax | CSRF 緩解 |
| SESSION_COOKIE_NAME | beakmask_session | 非預設名稱，避免指紋辨識 |

### 5.2 會話儲存與生命週期

| 項目 | 說明 |
|------|------|
| 儲存後端 | Production: Redis / Development: FileSystemCache |
| Production 有效期 | 4 小時 |
| Development 有效期 | 8 小時 |
| 多實例隔離 | Session 目錄名含專案路徑 hash，防止跨實例衝突 |

### 5.3 Flask-Login 會話保護

`session_protection = 'strong'`: IP 或 User-Agent 變動時自動登出，防止 session hijacking。

實作檔案: `backend/app/config.py`, `backend/app/__init__.py`

---

## 6. 速率限制與暴力破解防護 (Rate Limiting)

### 6.1 分層限制策略

| 分類 | 預設限制 | 說明 |
|------|---------|------|
| shared_login | 20 per 10 min | 共用登入頁 |
| org_login | 20 per 10 min | 企業登入頁 |
| vendor_login | 20 per 10 min | 外部廠商登入 |
| forgot_password | 3 per hour | 忘記密碼 (L1 嚴格) |
| reset_password | 5 per hour | 密碼重設 (L1 嚴格) |
| 全域預設 | 20000/day, 600/min | 一般 API (L3) |

### 6.2 智慧 Key 策略

| 使用者狀態 | Rate Limit Key | 解決問題 |
|-----------|---------------|---------|
| 已認證 | `user:{secure_code}` | 企業 NAT 共用 IP |
| 未認證 | 來源 IP | 一般防護 |

### 6.3 限制值配置

- DB 可配置（`rate_limit_configs` 表），支援動態調整
- 快取機制: 每 100 次請求重新讀取 DB
- 儲存: Redis (獨立 DB 1)

實作檔案: `backend/app/services/rate_limit_service.py`, `backend/app/config.py`

---

## 7. 輸入驗證與注入防護 (Input Validation)

### 7.1 SQL Injection 防護

| 措施 | 說明 |
|------|------|
| SQLAlchemy ORM | 所有查詢使用 ORM 參數化，無字串拼接 |
| ResourceGateway | 統一入口，Key 值從程式定義而非用戶輸入 |
| secure_code 格式驗證 | `^[A-Za-z0-9_-]{10,32}$`，格式不符直接 404 |
| Semgrep 規則 | `beakplatform-sql-injection` 自動掃描字串拼接 SQL |

### 7.2 Command Injection 防護

| 措施 | 說明 |
|------|------|
| Semgrep 規則 | `beakplatform-command-injection` 掃描 `shell=True` 和 `os.system()` |
| 程式碼中未發現 | `os.system()`, `os.popen()`, `subprocess.call(shell=True)` |

### 7.3 XSS 防護

| 措施 | 說明 |
|------|------|
| Jinja2 自動轉義 | 模板引擎預設啟用 auto-escaping |
| CSP 限制 | `Content-Security-Policy` 限制 inline script 來源 |

### 7.4 檔案上傳安全

| 措施 | 說明 |
|------|------|
| 副檔名白名單 | `{'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}` |
| 檔案大小限制 | 2MB |
| 安全檔名 | `werkzeug.secure_filename()` |
| 大小驗證 | seek-to-end 方式在儲存前驗證實際大小 |
| 檔名生成 | 使用 `org.secure_code` 作為檔名基礎，非用戶提供的檔名 |

實作檔案: `backend/app/api/enterprise_settings.py`

---

## 8. HTTP 安全標頭 (Security Headers)

### 8.1 應用層（Flask after_request）

| 標頭 | 值 | 防護 |
|------|-----|------|
| X-Frame-Options | SAMEORIGIN | Clickjacking |
| X-Content-Type-Options | nosniff | MIME sniffing |
| X-XSS-Protection | 1; mode=block | Legacy 瀏覽器 XSS |
| Referrer-Policy | strict-origin-when-cross-origin | Referrer 洩露 |
| Strict-Transport-Security | max-age=31536000; includeSubDomains | HTTPS 降級（Production） |
| Permissions-Policy | 關閉地理定位/麥克風/攝影機/支付/USB | 瀏覽器功能濫用 |
| Server | (移除) | 伺服器指紋隱藏 |

### 8.2 Content-Security-Policy (CSP)

| 指令 | 值 | 說明 |
|------|-----|------|
| default-src | 'self' | 預設只允許同源 |
| script-src | 'self' 'unsafe-inline' 'unsafe-eval' | 前端框架需求 |
| style-src | 'self' 'unsafe-inline' | 行內樣式需求 |
| img-src | 'self' data: https: | 圖片來源 |
| connect-src | 'self' | AJAX/Fetch 限制 |
| worker-src | 'self' blob: | ACE editor Web Worker |
| frame-ancestors | 'self' | 內嵌框架限制 |
| form-action | 'self' | 表單提交限制 |
| base-uri | 'self' | Base URL 限制 |

### 8.3 Nginx 層

| 設定 | 值 | 說明 |
|------|-----|------|
| client_max_body_size | 20M | 防止大檔案 DoS |
| proxy_connect_timeout | 30s | 連線逾時 |
| proxy_read_timeout | 60s | 讀取逾時 |
| proxy_send_timeout | 60s | 傳送逾時 |
| X-Real-IP / X-Forwarded-For | 設定 | 真實 IP 傳遞 |

實作檔案: `backend/app/security/security_headers.py`, `scripts/install.sh`

---

## 9. CSRF 防護

| 項目 | 說明 |
|------|------|
| 技術 | Flask-WTF CSRFProtect |
| Token 有效期 | 3600 秒 (1 小時) |
| Web 表單 | 自動注入 CSRF token |
| API 端點 | `@csrf.exempt`，依賴 session 認證 |
| 登入端點 | `@csrf.exempt`（登入前無 session 可被攻擊） |
| Cookie SameSite | Lax（額外防線） |

實作檔案: `backend/app/config.py`, `backend/app/__init__.py`

---

## 10. 資料加密與保護 (Data Protection)

### 10.1 密碼與 Token 雜湊

| 項目 | 演算法 | 說明 |
|------|--------|------|
| 用戶密碼 | bcrypt + auto salt | 時間常數比對 |
| 密碼歷史 | bcrypt | 防止重複使用 |
| 重設 Token | SHA-256 | `hmac.compare_digest()` 時間常數驗證 |
| secure_code | `secrets.token_urlsafe()` | 密碼學安全隨機，約 131 bits 熵 |
| SECRET_KEY | `secrets.token_hex(32)` | 安裝時自動生成 |

### 10.2 URL 識別碼安全

- 所有對外 URL 使用 `secure_code` 而非自增 ID
- 防止資源數量猜測與 IDOR 攻擊
- `to_dict()` 回傳 `secure_code`，不暴露內部 ID

### 10.3 PostgreSQL pgcrypto

安裝時啟用 `pgcrypto` 擴充，支援資料庫層級加密函式。

### 10.4 Secret Key 管理

| 環境 | 策略 |
|------|------|
| Production | 強制從環境變數讀取，缺少時拋出 `ValueError` 中斷啟動 |
| .env 檔案 | `chmod 600`，僅 service user 可讀 |
| 安裝時 | `secrets.token_hex(32)` 自動生成 |

---

## 11. 隱私與個資保護 (Privacy / PII)

### 11.1 個資遮罩工具

| 函式 | 效果 | 用途 |
|------|------|------|
| `mask_email()` | `user@example.com` -> `u***@e***.com` | 日誌/錯誤訊息 |
| `mask_ip()` | `192.168.1.100` -> `192.168.x.x` | 日誌/顯示 |
| `sanitize_filename()` | 移除危險字元，防路徑遍歷 | 檔案上傳 |

實作檔案: `backend/app/utils/security.py`

### 11.2 稽核日誌隱私

- 稽核日誌記錄 `user_secure_code`，不記錄密碼或敏感個資
- HTTP 存取日誌記錄 IP 但不記錄帳號資訊

### 11.3 帳號列舉防護

| 場景 | 防護措施 |
|------|---------|
| 登入失敗 | 帳號不存在與密碼錯誤回傳相同訊息 |
| 密碼重設 | 帳號不存在仍回傳「已發送驗證信」 |

### 11.4 軟刪除 (DATA-01)

- 所有刪除操作預設為軟刪除 (`is_deleted=True`)
- 查詢時必須過濾 `is_deleted=False` 和 `is_active=True`
- 保留資料完整性用於稽核追蹤
- `SoftDeleteMixin` 提供 `is_deleted` + `deleted_at` 欄位

實作檔案: `backend/app/models/base.py`

---

## 12. 稽核日誌 (Audit Logging)

### 12.1 資料庫稽核日誌

| 項目 | 說明 |
|------|------|
| 技術 | Flask `after_request` hook 寫入 `audit_logs` 表 |
| 三級制度 | MINIMAL (登入/登出) / STANDARD (含寫入操作) / VERBOSE (全部請求) |
| 可配置 | 企業可自訂稽核等級 |
| 快取 | 每 100 次請求重讀 DB 設定 |
| 記錄事件 | 未知網域登入、未知用戶登入、密碼錯誤、登入被拒、登入成功、權限違規 |

實作檔案: `backend/app/services/audit_service.py`, `backend/app/security/audit_logger.py`

### 12.2 HTTP 存取日誌

| 項目 | 說明 |
|------|------|
| 格式 | Apache Combined Log Format |
| 位置 | `/opt/tmp/BeakPlatform-access-{hash}.log` |
| 輪轉 | 50MB/檔，保留 5 份 |
| IP 取得 | CF-Connecting-IP > X-Forwarded-For > remote_addr |
| 排除 | 靜態資源不記錄 |
| 國家資訊 | 支援 Cloudflare 國家標頭 |

實作檔案: `backend/app/security/access_logger.py`

---

## 13. 部署安全 (Deployment Security)

### 13.1 系統帳號隔離

| 項目 | 說明 |
|------|------|
| Service User | `beakplatform` (system account, nologin shell) |
| 主群組 | `beakplatform` (非 root) |
| 權限 | 僅能存取 `/opt/BeakPlatform` 和 `/opt/tmp` |
| .env 權限 | `chmod 600`，僅 owner 可讀 |
| 安裝目錄 | `chown -R beakplatform:beakplatform` |

### 13.2 Gunicorn 安全設定

| 設定 | 值 | 說明 |
|------|-----|------|
| limit_request_line | 4094 | 最大 URL 長度 |
| limit_request_fields | 100 | 最大 header 數量 |
| limit_request_field_size | 8190 | 最大 header 大小 |
| max_requests | 1000 | Worker 處理 1000 請求後重啟（防記憶體洩漏） |
| max_requests_jitter | 50 | 隨機化重啟間隔 |
| timeout | 30s | 請求逾時 |
| preload_app | True | 共享記憶體 |

實作檔案: `backend/gunicorn.conf.py`

### 13.3 Nginx 反向代理

- Gunicorn 僅綁定 `127.0.0.1:8000`，不對外暴露
- Nginx 處理外部請求，轉發至 Gunicorn
- 靜態資源由 Nginx 直接提供，含 7 天快取
- 健康檢查端點不寫入存取日誌

### 13.4 Redis 會話隔離

- Session 使用 Redis DB 0
- Rate Limiting 使用 Redis DB 1
- 安裝時執行 `FLUSHDB` 清除舊 session

### 13.5 資料庫連線池

| 設定 | 值 | 說明 |
|------|-----|------|
| pool_pre_ping | True | 連線重用前健康檢查 |
| pool_recycle | 300s | 5 分鐘回收 |
| pool_size | 10 | 連線池大小 |
| max_overflow | 20 | 最大溢出連線 |

實作檔案: `backend/app/config.py`

---

## 14. 靜態分析與自動化檢查 (SAST)

### 14.1 Semgrep 安全規則

| 規則 ID | 嚴重度 | 掃描目標 |
|---------|--------|---------|
| beakplatform-missing-auth-decorator | ERROR | 路由缺少認證 decorator |
| beakplatform-direct-model-query-in-api | WARNING | API 層直接 Model.query |
| beakplatform-sql-injection | ERROR | SQL 字串拼接 |
| beakplatform-command-injection | ERROR | shell=True / os.system() |
| beakplatform-hardcoded-secret | ERROR | 硬編碼密鑰/密碼 |
| beakplatform-insecure-random | WARNING | 使用 random 而非 secrets |
| beakplatform-debug-enabled | WARNING | Production debug mode |
| beakplatform-insecure-pickle | WARNING | 反序列化不可信資料 |
| beakplatform-log-sensitive-data | WARNING | 日誌記錄密碼/token |

實作檔案: `.semgrep/beakplatform-security.yaml`

### 14.2 安全稽核記錄

定期進行安全稽核，已完成稽核記錄: `dev-notes/SECURITY_AUDIT_20260302.md`

已修復的安全問題:
- SEC-01 [Critical]: 租戶隔離違規 (`ModuleAccessService.remove_access()`)
- SEC-02 [Medium]: 孤立 MenuPermission 記錄
- SEC-03 [Medium]: 選單可見性設定錯誤
- SEC-04~06 [Low]: 前綴匹配/例外處理/遷移腳本修正

---

## 15. 安全設計原則 (Security by Design)

### 適用於本平台的安全原則

| 原則 | 實踐方式 |
|------|---------|
| Deny by Default | 全域認證攔截，白名單制 |
| Defense in Depth | ORM 過濾 + ResourceGateway + PostgreSQL RLS 三層租戶隔離 |
| Least Privilege | 獨立 service account，nologin shell，最小檔案權限 |
| Separation of Duties | SYSTEM_ADMIN 與 ORG_ADMIN 權限分離，不互相繼承 |
| Fail Secure | SECRET_KEY 缺少時中斷啟動，格式不符回 404 |
| No Security by Obscurity | secure_code 安全性基於密碼學隨機而非隱藏 |
| Complete Mediation | 每個請求都經過認證攔截器和角色守衛 |
| Audit Everything | 三級稽核日誌 + HTTP 存取日誌 |

---

## 安全措施架構圖

```
                      Internet
                         |
                    [ Nginx ]
                    Security Headers / Timeout / Body Size Limit
                         |
                    [ Gunicorn ]
                    Request Limits / Worker Lifecycle / Timeout
                         |
              +----------+-----------+
              |                      |
         [ before_request ]    [ after_request ]
         Auth Interceptor      Security Headers
         Rate Limiter          Audit Logger
         Tenant Context        Access Logger
         Page Role Guard
              |
         [ Decorators ]
         @login_required
         @admin_required
         @permission_required
         @module_access_required
              |
         [ ResourceGateway ]
         Tenant Filter
         secure_code Validation
         Protected Fields
              |
         [ SQLAlchemy ORM ]
         Parameterized Queries
              |
         [ PostgreSQL ]
         RLS Policies
         pgcrypto
```

---

*本文件為內部資安文件，不隨程式碼推送至 GitHub。*
