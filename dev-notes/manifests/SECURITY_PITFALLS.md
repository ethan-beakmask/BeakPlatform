# BeakPlatform 安全防雷指南

AI 修改程式前必讀。每個項目都是實際踩過的坑。

---

## 1. 租戶隔離 -- 最常踩的坑

### 規則
所有多租戶資料查詢必須包含 `org_secure_code` 過濾。

### 踩坑場景
```python
# 錯誤：跨租戶資料洩露
users = User.query.filter_by(is_active=True).all()

# 正確：明確指定企業
users = ResourceGateway.filter(
    User,
    org_secure_code=current_user.org_secure_code,
    is_active=True,
    is_deleted=False
)
```

### 容易忽略的地方
- 下拉選單的選項查詢（角色、部門、群組）
- 自動完成/搜尋建議
- 關聯查詢（透過 role 查 user 時，忘了 role 也要過濾 org）
- MenuRoleRequirement 查詢（必須加 org_secure_code）
- 匯出報表時的資料查詢

### API vs Web
- **平台 API 層**（`backend/app/api/`）且 model 已註冊：禁止 `Model.query`，必須用 `ResourceGateway`
- **模組 API 層**（`modules/*/api/`）：model 未註冊 gateway，沿用 `Model.query` ＋ 顯式
  `org_secure_code` 過濾（詳見 CLAUDE.md TENANT-02，**不要改寫成 ResourceGateway**）
- **Web 層**：允許 `Model.query` 但仍須加 `org_secure_code` 過濾
- **Service 層**：視呼叫者而定

### 比「有沒有走 gateway」更該查的
**org 值的來源**。`org_secure_code` 只能來自 `current_user` / `g.api_key` /
service account；**從 request body 或 query string 取 org 就是越權**，
不論有沒有走 gateway 都擋不住。

---

## 2. 帳號狀態過濾 -- 第二常見

### 規則
所有查詢用戶的地方，必須同時過濾 `is_deleted=False` 和 `is_active=True`。

### 踩坑場景
- 用戶列表忘記過濾 → 顯示已刪除/停用帳號
- 部門成員列表忘記 JOIN User 檢查 → 顯示已停用成員
- 角色指派時查候選人 → 列出已停用帳號
- 簽核人選擇 → 選到已離職企業成員

### 關聯查詢的陷阱
```python
# 錯誤：透過部門查成員，沒檢查用戶狀態
members = UserUnitMembership.query.filter_by(
    unit_secure_code=dept_sc
).all()

# 正確：JOIN User 確認帳號狀態
members = db.session.query(UserUnitMembership).join(
    User, UserUnitMembership.user_secure_code == User.secure_code
).filter(
    UserUnitMembership.unit_secure_code == dept_sc,
    UserUnitMembership.is_deleted == False,
    User.is_deleted == False,
    User.is_active == True
).all()
```

---

## 3. 雙鑰匙選單安全 -- 改了不該改的

### 規則
選單顯示問題的根因是 DB 資料設定，不是程式邏輯。

### 雙鑰匙機制（完整模型見 dev-notes/PERMISSION_MODEL.md）
- **Key1**: `menu_permissions` 表 -- 控制哪些 user_type 能看到選單（層界宣告）
- **Key2**: `menu_role_requirements` 表 -- 控制哪些角色能看到選單（按企業隔離，僅對 EMPLOYEE/EXTERNAL 生效；SYSTEM_ADMIN/ORG_ADMIN 依規則 bypass）
- （已退役）`menu_items.required_permission` 不再參與選單可見性，permission code 僅存在 API/資源層

### 禁止修改的檔案（選單問題時）
- `auth_interceptor.py`
- `page_permission_service.py`
- `page_role_guard.py`
- `menu_service.py` 的 `_resolve_link()`

### 正確排查流程
1. 查 `menu_items` 確認 link_type 是否正確（只認 url/route/page/divider/header）
2. 查 `menu_permissions` 確認 user_type 設定
   - 模組選單的 user_types 來源是模組 `__init__.py` 定義，改 DB 會被 `flask module sync --force` 沖掉
3. 查 `menu_role_requirements` 確認角色設定（含 org_secure_code）
   - 企業管理員可在 權限中央 → 功能視角 → 角色存取需求 [編輯] 自行設定（含企業自訂角色）
4. 查 `user_role_assignments` 確認用戶角色（含有效期限）
   - 注意：指派角色給 ORG_ADMIN 帳號無效果（bypass 角色檢查），應指派給其 EMPLOYEE 帳號

---

## 4. ResourceGateway -- 平台 API 強制、模組 API 不適用

### 規則
平台 API（`backend/app/api/`）中禁止直接 `Model.query`。

**模組 API（`modules/*/api/`）不在此列**：`MODEL_RESOURCE_TYPE_MAP` 一個模組 model
都沒註冊，經過 gateway 會被 fail-closed 拒絕。模組 API 的要求是
「顯式 org 過濾 ＋ 身分閘門 ＋ RLS」，完整說明見 CLAUDE.md TENANT-02。

### Semgrep 會抓
`.semgrep/beakplatform-security.yaml` 中有規則 `beakplatform-direct-model-query-in-api`
（**paths 已於 2026-08-16 限縮到 `backend/app/api/`**；在此之前是 `**/api/*.py`，
會對模組 API 噴出 300+ 條無人處理的 WARNING）。

### 正確用法
```python
# 取單一資源
item = ResourceGateway.get(User, secure_code)

# 過濾列表
items = ResourceGateway.filter(User, org_secure_code=org_sc, is_active=True)
```

### ResourceGateway 自動做的事
- secure_code 格式驗證（防 SQL injection）
- 租戶過濾（若 model 有 org_secure_code）
- 存取日誌（可選）

---

## 5. 時區處理 -- 顯示 UTC 而非本地時間

### 後端模板
```jinja2
{# 正確 #}
{{ record.created_at|tz_format('%Y-%m-%d %H:%M') }}

{# 錯誤：顯示 UTC 時間 #}
{{ record.created_at.strftime('%Y-%m-%d %H:%M') }}
```

### 前端 JS
```javascript
// 正確
BkTime.format(record.created_at, 'short')

// 錯誤：用瀏覽器時區
new Date(record.created_at).toLocaleString('zh-TW')
```

### 例外
純日期欄位（`effective_from`, `start_date` 等）不涉及時區，可用 `.strftime('%Y-%m-%d')`。

---

## 6. CSRF -- API vs 表單搞混

### 規則
- Web 表單：必須包含 CSRF token
- API 端點：標記 `@csrf.exempt`（用 session/token 認證）

### 踩坑場景
- 新增 API POST 端點忘記 `@csrf.exempt` → 前端 fetch/axios 呼叫失敗（403）
- 在表單路由上加 `@csrf.exempt` → CSRF 攻擊風險

---

## 7. 密碼處理 -- 絕對不能明文

### 規則
- 儲存：bcrypt hash
- 驗證：`user.check_password(password)`
- 重設：檢查密碼歷史（`password_history` 表）
- 日誌：絕對不記錄密碼明文

### 密碼策略
企業可自訂策略（長度、複雜度、歷史次數、鎖定規則），查詢方式：
```python
PasswordPolicyService.get_policy(org_secure_code)
```

---

## 8. Secure Code -- 不用自增 ID

### 規則
- URL 中只能用 `secure_code`，不用自增 ID
- 格式：`^[A-Za-z0-9_-]{10,32}$`
- ResourceGateway 自動驗證格式

### 踩坑場景
- 新增路由時用 `<int:id>` → 洩露資源數量、可猜測
- 前端拼 URL 時直接用數字 ID

---

## 9. 企業獨立資料庫 -- 連線隔離

### 機制
- 企業有獨立的資料庫實例（透過 `FwOrgDatabase`）
- 集團有共享資料庫（`Conglomerate.shared_db_*`）
- 連線透過 `pool.get_org_conn(org_secure_code)` 取得

### 踩坑場景
- 用主 DB 連線查企業獨立 DB 的表 → 找不到表或跨企業
- 日誌中洩露企業 DB 的連線密碼
- API 回傳中包含 `shared_db_password_encrypted`

---

## 10. PII 個資防護 -- 遮罩與限制

### 現有工具
```python
from app.utils.security import mask_email, mask_ip

mask_email('user@example.com')  # u***@e***.com
mask_ip('192.168.1.100')        # 192.168.x.x
```

### 必須遮罩的場景
- 審計日誌中的 email、IP
- API 錯誤訊息中的用戶資訊
- 向低權限用戶顯示高權限用戶的資訊

### 預計開發中
- 懶捲動（lazy scroll）：用戶捲動才傳到前端
- UI 隱私遮罩：欄位視覺打碼，滑鼠懸停才顯示

---

## 11. 軟刪除 -- 永遠記得過濾

### 所有繼承 BaseModel 的實體都有 `is_deleted` 欄位

### 容易忘記的地方
- 下拉選單的選項來源
- 自動完成的候選清單
- 組織樹/部門樹的節點
- 統計/報表的資料查詢
- 匯出功能

---

## 9. 資料出口政策 (Egress) -- 遮罩欄位與 Master-Detail

規格：`dev-notes/EGRESS_POLICY_SPEC.md`。設有出口政策的資源，欄位可能是
`masked`（下發哨兵，真值不離開伺服器）或 `hidden`（投影剔除）。

```python
# 錯誤：新增序列化路徑繞過出口政策（masked 欄位裸奔）
return jsonify({'users': [u.to_dict() for u in users]})

# 正確：to_dict 之後過 egress_service.apply
from app.services import egress_service
return jsonify({'users': egress_service.apply('user', 'list', [u.to_dict() for u in users])})
```

**鐵律**：
- **Master-Detail 禁止在 list 回應內嵌預載 detail 資料**——detail 必須由
  獨立 API 呼叫取得，否則 detail 語境的政策評估被繞過
- masked 欄位唯一取值通道是 `POST /api/egress/reveal`，禁止另開端點回傳真值
- 遮罩必須做在伺服器端投影；只靠 Form.io hidden/conditional 或前端 CSS
  隱藏 = 值已在瀏覽器，不是護欄
- export/匯出路徑必須同樣過政策（通常最容易被遺忘的破口）

已接入資源（改這些 API 時注意保持 apply 呼叫）：`user`（users list/detail
API + `/users/<sc>` 檢視頁 Jinja `egress_value`/`egress_visibility`）

---

## 修改前自查清單

每次修改程式前，逐項確認：

- [ ] 新路由有認證 decorator
- [ ] 平台 API 使用 ResourceGateway（模組 API 沿用既有 Model.query 寫法）
- [ ] 查詢包含 org_secure_code 過濾，且 org 值來自登入身分而非 request 輸入
- [ ] 用戶查詢加 is_deleted=False, is_active=True
- [ ] datetime 顯示用 tz_format / BkTime.format
- [ ] API POST 端點有 @csrf.exempt
- [ ] 沒有硬編碼密碼/密鑰
- [ ] 沒有 SQL 字串拼接
- [ ] 日誌不含明文 PII
- [ ] URL 用 secure_code 不用自增 ID
- [ ] 有出口政策的資源，新序列化路徑過 egress_service.apply；list 回應不內嵌 detail
