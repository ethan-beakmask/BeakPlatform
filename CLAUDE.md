# BeakPlatform - Claude Code 專案規範

## 專案定位

**BeakPlatform 是一個多租戶權限管理平台**

這是一個**純平台**，核心功能：
- 安全控制（認證、授權、攔截）
- 多租戶隔離（企業資料隔離、RLS）
- RBAC 權限系統
- 動態選單系統
- 組織架構管理（部門、群組、角色）
- 人資架構管理（職等、職系、職稱）

**業務功能透過「模組」掛載，不在平台內實作。**

---

## 溝通對照表

用戶提到系統功能時，參照 `docs/GLOSSARY.md` 快速定位。

用戶溝通慣例：
- `/path/` — URL 路徑（如 `/menu/` = `http://192.168.0.16:7000/beakplatform/menu/`，**app 掛在 nginx 的 `/beakplatform` 前綴下，缺前綴會 404**）
- `'名詞'` — 功能名稱或字串，多名詞時混用 `""` 區別
- `[按鈕]` — UI 按鈕或超連結元素
- `(URL)` — 從瀏覽器複製的完整 URL

---

## 每次對話必做

### 1. Git Commit (對話結束)
**每次對話結束前**：

```bash
cd /opt/BeakPlatform-dev
git add -A
git commit -m "類型: 簡短摘要

- 完成項目 1
- 完成項目 2

Generated with Claude Code"
```

**注意：commit 和 push 是兩件事。只 commit，不主動 push。用戶說 push 才 push。**

**GitHub 推送必須使用過濾腳本：**
- **push** → `git push origin main` (Forgejo，直接推)
- **push github** → `bash scripts/push_github.sh` (GitHub，過濾推送)
- **push both** → 先 `git push origin main`，再 `bash scripts/push_github.sh`
- **禁止** 直接執行 `git push github main`，會把 CLAUDE.md 等內部檔案推上去
- 過濾腳本要求工作區乾淨，有未 commit 的變更時先 `git stash --include-untracked`，推完再 `git stash pop`
- GitHub 的 history 與 origin 不同步是正常的（過濾 commit），不要 merge github/main 回 local

### 2. 更新追蹤
- 完成 Forgejo Issue 時，用 API 關閉：`curl -X PATCH ... -d '{"state":"closed"}'`
- 如果涉及架構變更，更新相關文件

---

## Manifest 導向開發流程（強制）

**所有程式修改必須先查 manifest，禁止盲目探索。**

### 流程

1. **收到工單** → 讀 `docs/manifests/README.yaml` 找到目標 manifest
2. **讀 manifest** → 取得精確的檔案清單（route、api、service、model、template、js）
3. **只讀 manifest 列出的檔案** → 在這些檔案中定位問題並修正
4. **如果不夠** → 向用戶說明需要查看哪些額外檔案及原因，等確認後再讀

### 禁止

- **禁止** 收到 URL 後自行 grep/glob 搜尋相關程式（manifest 已列出）
- **禁止** 在 manifest 範圍外自行讀取檔案（除非向用戶說明並獲同意）
- **禁止** 修改 `security-core.yaml` 列出的安全核心檔案（除非用戶明確要求）

### 安全防雷

修改程式前必須查閱 `docs/manifests/SECURITY_PITFALLS.md`，確認不踩以下坑：
- 租戶隔離（org_secure_code 過濾）
- 帳號狀態過濾（is_deleted + is_active）
- ResourceGateway 使用（API 層禁止 Model.query）
- 雙鑰匙選單安全（MenuPermission + MenuRoleRequirement）
- 時區處理（TZ-01 規範）

### 工單格式

用戶會以此格式提交工單：
```
目標頁面: /users/
問題類型: bug | 功能調整 | 新增欄位 | UI 修正
症狀: （問題描述）
影響範圍: list / create / edit / view
已知線索: （選填）
```

完整工單模板見 `docs/manifests/TICKET_TEMPLATE.md`。

---

## 當前開發階段

平台基礎建設與模組化標準已完成。目前處於**功能完善階段**。

待辦事項追蹤在 [Forgejo Issues](http://192.168.0.16:3000/forgejoadmin/BeakPlatform/issues)。
架構與模組化標準詳見 `docs/PLATFORM_MODULARIZATION_PLAN.md`。

---

## 安全標準 (必須遵守)

### AUTH-01: 全域認證攔截
- 所有請求經過 `before_request` 認證檢查
- 未登入訪問非白名單路由 → 401

### AUTH-02: 統一認證 Decorator
```python
@public_route          # 公開路由
@login_required        # 需要登入
@admin_required        # 需要企業管理員
@system_admin_required # 需要系統管理員
```

### PERM-01: 權限模型（4+1）
- 四層 user_type 硬界線（角色永不跨層）+ NoCode 公開資料隔離區
- 選單/頁面 = 雙鑰匙（Key1 user_type 層界 + Key2 角色，僅 EMPLOYEE/EXTERNAL 吃 Key2）；欄位 = EGRESS-01
- `menu_items.required_permission` 已退役不再影響選單；permission code 僅存在 API/資源層
- 定版文件：`docs/PERMISSION_MODEL.md`（bypass 規則、功能開放多層 SOP、已知備忘）

### TENANT-01: 強制企業隔離
- 所有查詢包含 `org_secure_code` 過濾
- PostgreSQL RLS 作為最後防線

### TENANT-02: ResourceGateway 要求
- API 層禁止直接使用 `Model.query`
- 必須透過 `ResourceGateway` 存取

### DATA-01: 帳號查詢必須過濾刪除與停用
- **所有查詢用戶/帳號的地方**，必須同時過濾 `is_deleted=False` 和 `is_active=True`
- 包含但不限於：用戶列表、組織樹、簽核人選擇、角色成員解析、部門成員解析
- 關聯查詢（如透過角色/部門取用戶）需 JOIN User 表確認帳號狀態

### EGRESS-01: 資料出口政策

設有出口政策的資源，欄位依 (角色, 語境) 呈現 clear / masked / hidden。
規格：`docs/EGRESS_POLICY_SPEC.md`，防雷：`docs/manifests/SECURITY_PITFALLS.md` 第 9 節。

- API 序列化：to_dict 之後過 `egress_service.apply(resource, context, items)`
- 後端模板：`egress_value()` / `egress_visibility()` template globals + `BkEgress.bind()`
- **禁止** list 回應內嵌預載 detail 資料（master-detail 必須分開請求）
- **禁止** 繞過 `POST /api/egress/reveal` 另開端點回傳 masked 欄位真值

### MENU-01: 選單項目新增規範

**新增 menu_items 記錄時，必須遵守以下規則：**

**link_type 有效值**（`_resolve_link()` in `menu_service.py` 只認以下值）：

| link_type | link_target 格式 | 說明 |
|-----------|-----------------|------|
| `url` | `/security/alert-broadcasts/` | 直接 URL 路徑（最常用） |
| `route` | `admin.settings` 或 `/path/` | Flask endpoint 名稱，或以 `/` 開頭的路徑 |
| `page` | `page_secure_code` | 動態頁面，自動加 `/p/` 前綴 |
| `divider` | （空） | 分隔線 |
| `header` | （空） | 群組標題 |

**其他 link_type 值（如 `path`）會導致 href 變成 `#`，選單點了沒反應。**

**參考既有同類選單**：新增前先查 DB 中同層級或同功能的選單用什麼 link_type，照著用。
```sql
SELECT code, link_type, link_target FROM menu_items WHERE parent_secure_code = '目標父選單SC';
```

**禁止事項**：
- **禁止** 為了「選單無法點擊」而修改 `menu_service.py` 的 `_resolve_link()` -- 問題一定出在 DB 的 link_type 設定
- **禁止** 為了選單顯示問題而修改權限控制邏輯（`auth_interceptor`、`page_permission_service`、`page_role_guard`）-- 這些是安全核心，選單顯示異常的根因是 DB 資料設定錯誤

### FILE-01: 檔案上傳/下載統一規範

**所有檔案操作必須透過統一元件，禁止自行實作上傳/下載邏輯。**

#### 架構總覽

```
前端 BkFileAttachment → POST /api/files/upload → file_service.upload_file()
                                                      ├── local (org_logo, wf_background)
                                                      └── encrypted (form_attachment, subsystem_file)
                                                           └── crypto/key_manager.py (AES-256-GCM)
```

#### 加密機制 (內建，非外部服務)

- **位置**: `backend/app/crypto/` (engine.py + key_manager.py)
- **演算法**: AES-256-GCM
- **金鑰架構**: Master Key (env) → Org Key (DB per 企業) → File DEK (per 檔案隨機)
- **觸發時機**: `storage_type='encrypted'` 時自動加解密，程式不需手動呼叫加密函式
- **加密檔案儲存**: `ENCRYPTED_STORAGE_DIR` 環境變數指定的目錄，按企業隔離子目錄

#### context_type 與 storage_type 對應

| context_type | storage_type | 加密 | 說明 |
|---|---|---|---|
| `org_logo` | `local` | 否 | 企業 Logo |
| `wf_background` | `local` | 否 | 工作流設計器底圖 |
| `form_attachment` | `encrypted` | 是 | 表單簽核附件 |
| `subsystem_file` | `encrypted` | 是 | 子系統業務附件 |

**新增 context_type 時**：在 `file_service.py` 的 `CONTEXT_STORAGE_MAP`、`CONTEXT_ALLOWED_EXT`、`CONTEXT_MAX_SIZE` 三個 dict 中加入對應設定。

#### 後端開發 - 上傳

```python
from app.services import file_service

record = file_service.upload_file(
    org_sc=org.secure_code,       # 企業 SC (租戶隔離)
    file=request.files['file'],   # werkzeug FileStorage
    context_type='form_attachment', # 用途類型 → 自動決定加不加密
    context_id='RECORD_SC',       # 關聯的業務記錄 SC (選填)
    uploader_sc=current_user.secure_code,
)
db.session.commit()
# record.secure_code 用於前端存取
# record.serve_url / record.download_url 用於產生連結
```

#### 後端開發 - 下載/讀取

```python
record = file_service.get_file_by_sc(secure_code, org_sc=org.secure_code)
data, mime_type, original_name = file_service.serve_file(record)
# data 是明文 bytes，加密檔案已自動解密
```

#### 後端開發 - 刪除

```python
file_service.delete_file(record)  # 刪除實體檔案 + 軟刪除 DB 記錄
db.session.commit()
```

#### 前端開發 - BkFileAttachment 元件

```html
<script src="/static/js/bk-file-attachment.js"></script>
<div id="attachments"></div>
<script>
const att = new BkFileAttachment('#attachments', {
    contextType: 'form_attachment',
    contextId: '{{ record.secure_code }}',
    readonly: false,
    maxFiles: 10,
    onUpload: (file) => { /* 上傳完成 */ },
    onDelete: (fileSc) => { /* 刪除完成 */ },
});
att.init();
</script>
```

#### 禁止事項

- **禁止** 繞過 `file_service` 直接讀寫 uploads/ 或 encrypted_storage/ 目錄
- **禁止** 在前端自行實作上傳 API 呼叫（應使用 `BkFileAttachment`）
- **禁止** 手動呼叫 `crypto/engine.py` 加解密檔案（應透過 `file_service` 自動處理）
- **禁止** 將 `ENCRYPTION_MASTER_KEY` 硬編碼或寫入版控

---

## 專案結構

```
/opt/BeakPlatform-dev/
├── backend/
│   ├── app/
│   │   ├── security/       # 安全核心（勿隨意修改）
│   │   ├── crypto/         # 檔案加密模組 (AES-256-GCM)
│   │   ├── api/            # API 路由
│   │   ├── web/            # Web 路由
│   │   ├── models/         # 資料模型
│   │   ├── services/       # 業務邏輯
│   │   └── templates/      # Jinja2 模板
│   └── tests/
├── modules/                # 模組目錄
├── docs/
│   ├── GLOSSARY.md                    # 溝通對照表
│   ├── PLATFORM_MODULARIZATION_PLAN.md  # 架構與模組化標準
│   └── archive/                       # 已完成的歷史文件
├── scripts/
│   └── migrations/         # 資料庫遷移
└── .semgrep/               # 安全規則
```

---

## 模組靜態檔案規範

模組的 JS/CSS/圖片等靜態資源由 `module_loader.py` 自動註冊 serve。

**目錄結構：**
```
modules/<module_name>/static/modules/<module_name>/
  ├── js/           # JavaScript
  ├── css/          # 樣式表
  └── icons/        # 圖示
```

**存取 URL：** `/static/modules/<module_name>/js/xxx.js`

**禁止** 將模組靜態檔案複製到 `backend/app/static/`。
`backend/app/static/` 只放平台級資源（themes.css、vendor/、auth.js 等）。
模組資源一律放在 `modules/<name>/static/` 下，由 module_loader 自動 serve。

---

## 前端開發規範

### FRONT-01: JS/CSS 分離原則

**HTML 模板中禁止大量內嵌 JS/CSS。** 邏輯和樣式應盡量抽為獨立檔案。

| 類型 | 規範 | 說明 |
|------|------|------|
| CSS | 抽為 `.css` 靜態檔 | 放在 `static/` 目錄，用 `<link>` 引入 |
| JS 邏輯 | 抽為 `.js` 靜態檔 | 放在 `static/js/`，用 `<script src>` 引入 |
| 小段膠水代碼 | 可留在 HTML | 如初始化呼叫、Jinja2 變數注入（不超過 30 行） |

**平台層靜態檔位置：** `backend/app/static/js/`、`backend/app/static/css/`
**模組層靜態檔位置：** `modules/<name>/static/modules/<name>/js/`、`modules/<name>/static/modules/<name>/css/`

#### JS 抽離三種模式（依 Jinja2 耦合程度選擇）

**模式 A：直接搬移**（JS 零 Jinja2 變數）
```html
<!-- HTML: 只留引入 -->
<script src="/static/.../page.js"></script>
<div x-data="pageManager()">...</div>
```
範例：`template-list.js`、`workflow-list.js`

**模式 B：Window Bridge**（少量 Jinja2 變數需注入）
```html
<!-- HTML: 變數橋接 + 引入 -->
<script>
window.__PAGE_CONFIG = {
    scheduleId: '{{ schedule.secure_code }}',
    year: {{ year }}
};
</script>
<script src="/static/.../page.js"></script>
```
```js
// page.js: 讀取橋接變數
const config = window.__PAGE_CONFIG || {};
function pageManager() {
    return { scheduleId: config.scheduleId, year: config.year, ... };
}
```
範例：`holidays.js`、`schedules.js`、`form-center.js`

**模式 C：保留 Partial**（JS 與 Jinja2 深度交織）
維持 `{% include "_xxx_methods.html" %}` 模式，僅抽離 CSS。
此模式僅用於 JS 和 Jinja2 無法乾淨分離的情況，應盡量避免。

### FRONT-02: HTML 模板行數上限

- 單一 HTML 模板不應超過 **500 行**（含 HTML + 內嵌 JS/CSS）
- 超過時必須拆分：CSS → 靜態檔、模態框 → `_*_modals.html`、JS → `.js` 靜態檔或 `_*_methods.html` partial
- 參考已完成的拆分模式：`form_center.html`、`departments.html`、`form_designer.html`

### FRONT-03: Node Type 定義禁止硬編碼

- **禁止**在 API 程式碼中硬編碼 node type 定義
- `workflow_node_definitions` DB 表是 **single source of truth**
- API 透過 `WorkflowNodeDefinition` ORM Model 查詢
- 新增 node type 流程見 `docs/archive/NODE_TYPE_NORMALIZATION_PLAN.md`

### FRONT-04: Code 欄位自動建議規範

所有需要唯一識別碼 (code) 的建立表單，必須遵循統一 UX:

1. 輸入名稱 → debounce 500ms → 呼叫 `/api/code/generate` 取得建議
2. code 欄位顯示建議值為 placeholder，附建議列表按鈕
3. 使用者可手動輸入任意大小寫，即時呼叫 `/api/code/validate` 驗證
4. code 留空提交時，後端自動採用建議值
5. 不強制大小寫轉換（自動產生的建議為大寫，但不限制手動輸入）

**通用 API**:
- `POST /api/code/generate` -- body: `{ entity_type, name }`
- `POST /api/code/validate` -- body: `{ entity_type, code }`

**前端實作**:
- 引入 `/static/js/code-input.js`，使用 `codeInputMixin(entityType)`
- 可用 `{% include "partials/_code_input.html" %}` 取得標準建議區塊 HTML

---

### FRONT-05: 對話窗 (Modal) 表單元素規範

**CSS 全寬規則必須排除 radio 和 checkbox：**

```css
/* 正確 — 排除 radio/checkbox */
.stu-field input:not([type="radio"]):not([type="checkbox"]),
.stu-field select,
.stu-field textarea {
    width: 100%;
}

/* 錯誤 — radio/checkbox 會被撐到 100% 寬，擠壓同列文字成直排 */
.stu-field input { width: 100%; }
```

**Modal 尺寸設定：**
- 使用 inline style 覆蓋 CSS 預設寬度（如 `style="width:500px;"`）
- 若 CSS class 定義了 `width`，inline style 優先級更高，正常情況可覆蓋
- 內含表單的 Modal 建議最小寬度 450px，避免欄位過窄

**常見踩坑：**
- `input { width: 100% }` 會影響所有 input 類型，包括 radio、checkbox
- Radio/checkbox 被撐寬後，同列的 label 文字會被擠成直排或換行
- 解法：CSS selector 加 `:not([type="radio"]):not([type="checkbox"])` 排除

### FRONT-06: Alpine.js x-show 與 display 衝突規範

**禁止在有 `x-show` 的元素上用 inline style 設定 `display` 屬性。**

原因：Alpine.js `x-show` 透過切換 inline `display: none` 控制顯隱。
還原時會清除 inline display，導致原本的 `display: flex` 等值遺失，
元素退回 `<div>` 預設的 `display: block`。

正確做法：將 `display: flex` 等佈局屬性寫在 CSS class 中，
讓 `x-show` 只操作 inline display 而不影響 class 定義的佈局。

```html
<!-- 錯誤 - x-show 還原時 display:flex 會遺失 -->
<div x-show="visible" style="display:flex; flex-wrap:wrap; gap:8px;">

<!-- 正確 - 佈局屬性寫在 CSS class -->
<div x-show="visible" class="my-flex-container">
```

### FRONT-07: 模組 CSS 命名與排版規範

**平台未載入 Bootstrap，禁止在模板中使用 Bootstrap class。**

平台全域 CSS 為 `common.css` + `base-layout.css`，提供按鈕（`.btn`）、表格（`.data-table`）、
表單（`.form-control`）、Modal（`.modal-overlay`）等基礎元件，但**沒有 Grid 系統**
（無 `row`、`col-md-*`、`container-fluid`）。

**模組 CSS 開發規則：**

| 規則 | 說明 |
|------|------|
| 模組專屬前綴 | 所有 class 使用模組前綴（`vlc-`、`fw-` 等），避免與 common.css 撞名 |
| 排版方式 | CSS Grid / Flexbox（非 Bootstrap grid） |
| 區塊容器 | `xxx-section` + `xxx-section-header`（白底 + 1px border） |
| 統計卡片 | `xxx-stats` 用 `display: grid; grid-template-columns: repeat(N, 1fr)` |
| 雙欄佈局 | `xxx-grid-2` 用 `display: grid; grid-template-columns: 1fr 1fr; gap: 16px` |

**參考實作：** `modules/form_workflow/static/modules/form_workflow/css/fw-dashboard.css`

**常見錯誤（會導致排版全部擠在一起）：**
- 使用 `row` + `col-md-6`（不存在，無效果）
- 使用 `card` + `card-header` + `card-body`（common.css 無此定義）
- 使用 `table-sm`、`table-hover`（應用 `data-table` 或模組自訂 `xxx-table`）
- 使用 `mb-3`、`p-0`、`d-flex` 等 Bootstrap utility class

### CACHE-01: 靜態資源 Cache-Busting

**Flask 全站機制，確保 JS/CSS 變更後瀏覽器立即載入新版，無需 F5。**

實作位置：`backend/app/__init__.py` 的 `register_static_cache_busting()`

| 層 | 覆蓋範圍 | 原理 |
|---|---|---|
| `url_defaults` | `url_for('static', ...)` 引入的檔案 | 自動附加 `?v=<啟動時間戳>`，重啟服務即換版本號 |
| `after_request` | 裸路徑 `/static/...` 引入的檔案 | JS/CSS 回應加 `Cache-Control: no-cache, must-revalidate`，強制條件請求 |

**開發時注意事項：**
- 兩種引入方式都已涵蓋，新增模板時用哪種都可以
- 檔案有變更 -> 瀏覽器拿 200 新內容；沒變更 -> 304（不浪費頻寬）
- 重啟 Flask 後版本號自動更新

---

## 多語系規範 (I18N-01)

**平台支援 zh-TW（原文即 key）+ en，其他語系由社群擴展。所有新 user-facing 字串必須包翻譯函式：**

| 語境 | 寫法 | 帶變數 |
|------|------|--------|
| Python (flash/jsonify error/abort) | `from flask_babel import gettext as _` + `_('中文')` | `_('共 %(n)s 筆', n=x)` |
| Jinja2 模板 | `{{ _('中文') }}` | `{{ _('共 %(n)s 筆', n=x) }}` |
| JS（靜態檔、模板 script、Alpine 表達式） | `__('中文')`（i18n.js 全域） | `__('共 {n} 筆', {n: x})` |

**地雷與禁忌**：
- msgid 含字面 `%` 必須寫 `%%`（flask_babel 一律做 % 插值，裸 % 直接 500）
- **禁止**包裹：logger/console 訊息、寫入 DB 的資料值、email 主旨內文、參與 `==`/`===` 比較的字串（後端包了 `_()` 後，前端比對同字串即失效——改回穩定布林/代碼欄位）
- pybabel update 產生的 fuzzy 配對幾乎全是錯的，必須逐條重翻並清除 fuzzy flag

**翻譯流程**（新增字串後）：
```bash
cd /opt/BeakPlatform-dev/backend
../venv/bin/pybabel extract -F babel.cfg -k _l -o translations/messages.pot . \
  ../modules/open_defense ../modules/vuln_lifecycle ../modules/spec_formulate \
  ../modules/nocode_builder ../modules/form_workflow
../venv/bin/pybabel update -i translations/messages.pot -d translations -l en
# 補翻 translations/en/LC_MESSAGES/messages.po 後
../venv/bin/pybabel compile -d translations   # 改完重啟服務生效
```
- **extract 必須帶齊上列全部已包裹模組目錄**——少帶任何一個，該模組的 msgid 會被 update 打成 obsolete 並喪失翻譯（已發生過一次事故）。新模組包裹後要加進此清單
- JS 字典：`backend/app/static/i18n/en.json`（zh 原文 → en，flat dict / indent=1 / sort_keys），由 `/i18n/<locale>.js` 路由阻塞式載入
- 獨立模板（不繼承 base.html，如 studio.html、workflow_designer.html、form_designer.html）需自行載入 i18n.js + 語系字典區塊；`BkI18n` 是 top-level const 不掛 window，JS 判斷用 `typeof BkI18n !== 'undefined'`
- FormIO 設計器/渲染的 `language` 選項必須跟隨用戶 locale，非 zh-TW 不可載入 formio-i18n-zh-TW.json（會把英文反向翻回中文）
- 選單標題屬 DB 資料（menu_items.title_i18n JSONB），不走 gettext
- 詳細計畫與進度：`docs/I18N_PLAN.md`

## 時區處理規範 (TZ-01)

### 儲存層
- DB 一律使用 `datetime.utcnow()` 儲存 UTC 時間
- PostgreSQL 時區設定為 `Etc/UTC`，欄位類型 `timestamp without time zone`
- **純日期欄位**（`effective_from`、`start_date`、合約日期等）不涉及時區，直接存日曆日期

### 時區優先順序
`g.timezone` 由 `auth_interceptor.py` 設定：**用戶個人 > 企業設定 > `Asia/Taipei`**

### 後端模板顯示
- **必須** 使用 `|tz_format` filter 顯示 datetime 欄位
- **禁止** 直接 `.strftime()` 格式化 datetime 欄位（會顯示 UTC 時間）
- 純日期欄位可用 `.strftime('%Y-%m-%d')`（不需時區轉換）

```jinja2
{# 正確 #}
{{ record.created_at|tz_format('%Y-%m-%d %H:%M') if record.created_at else '-' }}

{# 錯誤 - 會顯示 UTC 時間 #}
{{ record.created_at.strftime('%Y-%m-%d %H:%M') }}
```

### 後端 API 回傳
- 若回傳已格式化時間字串：先將 UTC 轉為用戶時區再 `strftime`
- 若回傳 `isoformat()`：前端用 `BkTime.format()` 處理

```python
from zoneinfo import ZoneInfo
from flask import g

utc_tz = ZoneInfo('UTC')
user_tz = ZoneInfo(getattr(g, 'timezone', 'Asia/Taipei'))
local_dt = dt.replace(tzinfo=utc_tz).astimezone(user_tz)
```

### 前端 JS 顯示
- **必須** 使用 `BkTime.format(dateStr, style)` 格式化 DB 時間
- **禁止** 用 `new Date(x).toLocaleString()` 顯示 DB 時間（會用瀏覽器時區）
- `timezone.js` 已在 `base.html` 全域載入，`BkTime` 全站可用
- style: `'full'`(預設), `'short'`, `'date'`, `'time'`

```javascript
// 正確
BkTime.format(record.created_at, 'short')

// 錯誤 - 會用瀏覽器時區
new Date(record.created_at).toLocaleString('zh-TW')
```

- **自行做時間運算**（SLA 倒數、時間差）時，DB 回傳的 ISO 字串是 naive UTC（無 `Z` 後綴），
  直接 `new Date(iso)` 會被當本地時間、差 8 小時——必須先補 `Z` 再 parse（已踩過：SLA 顯示逾時 465 分）
```javascript
const iso = s.endsWith('Z') ? s : s + 'Z';   // naive UTC 補 Z
const deadline = new Date(iso).getTime() + slaMinutes * 60000;
```

---

## 禁止事項

1. **禁止** 繞過認證攔截器
2. **禁止** API 直接查詢 Model
3. **禁止** 在 URL 使用自增 ID
4. **禁止** 硬編碼密鑰/密碼
5. **禁止** SQL 字串拼接
6. **禁止** 在平台內實作業務功能（應透過模組）
7. **禁止** 將模組靜態檔案複製到 `backend/app/static/`（會造成雙份不同步）
8. **禁止** 在 API 程式碼中硬編碼 node type 定義（應查 DB）
9. **禁止** HTML 模板內嵌大量 JS/CSS（應抽為獨立靜態檔或 partial）
10. **禁止** 後端模板直接 `.strftime()` 顯示 datetime 欄位（應用 `|tz_format`，參見 TZ-01）
11. **禁止** 前端 JS 用 `new Date().toLocaleString()` 顯示 DB 時間（應用 `BkTime.format()`，參見 TZ-01）
12. **禁止** 繞過 `file_service` 直接操作檔案儲存目錄（參見 FILE-01）
13. **禁止** 手動呼叫 `crypto/engine.py` 加解密（應透過 `file_service` 自動處理）
14. **禁止** 在有 `x-show` 的元素上用 inline style 設定 `display`（應用 CSS class，參見 FRONT-06）

---

## 資料庫資訊

- **Host**: localhost
- **Port**: 5432
- **Database**: beakplatform_dev
- **User**: beakplatform
- **Password**: postgres123（開發環境）
- **本機資料皆為測試資料**：變更後可忽略舊資料，不用修正舊資料，除非用戶要求

---

## 備忘

### Forgejo
- **URL**: http://192.168.0.16:3000/
- **Repo**: http://192.168.0.16:3000/forgejoadmin/BeakPlatform
- **API Token**: `be6f8e52f155aa026ac12c5bd470114aa7c54333`

### 開發測試登入（本開發機獨有）
- **快速切換帳號（免密碼）**: `http://192.168.0.16:7000/beakplatform/dev/quick-login`，點帳號即登入
- **用完必按該頁 [登出] 按鈕**（曾發生登出不乾淨，該按鈕即為補救設計）
- SYSTEM_ADMIN 唯一帳號: `admin@system.local`（密碼不明，不要用猜的，會鎖定）
- curl 自動化登入（E2E 用，JSON 版；表單版有防機器人三欄位，勿用）:
  ```bash
  BASE=http://192.168.0.16:7000/beakplatform
  curl -s -c cj.txt -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
    -d '{"account":"admin-ethanyu@beluga.com","password":"ApiKeyTest2026"}'
  ```
- curl 打非 exempt 的 POST API 需要 CSRF token，從任一登入後頁面的 meta 取（登入回應不含 token）：
  ```bash
  TOKEN=$(curl -s -b cj.txt -c cj.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
  curl -s -b cj.txt -X POST "$BASE/api/xxx" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" -d '{...}'
  ```

### form_workflow 發行（publish）陷阱
- `POST /api/mappings/<sc>/publish` 以表單/流程模板的 **version+revision** 判斷有無變更；
  直接改 `fw_workflow_templates.graph`（SQL 或 PUT API）**不會** bump revision，
  publish 會回「版本未變更」並沿用舊快照
- 解法：改完 graph 先 `UPDATE fw_workflow_templates SET revision = revision+1 WHERE ...` 再 publish
- intake / 表單中心都只讀 `fw_published_form_workflows` 最新 Published 快照，改模板不重發行等於沒改
- 流程變數：流程編號（OD-YYYYMMDD-NNNN）是 `${wi.exec_code}`；`${wi.code}` 是 workflow instance 的 secure_code，
  沒有 `${wi.execution_code}` 這個變數（替換結果為空字串）

### 服務啟動
- **正式管道是 systemd 服務**：`sudo systemctl restart beakplatform-dev.service`（重啟後 `systemctl is-active` 確認）
- 開發服務以**非 debug 模式**跑，Python/模板變更**不會自動重載，必須重啟**
- **踩坑**：若曾手動 `flask run`，殘留進程會佔住 7000 埠導致 systemd 服務 crash loop（`is-active` 一直是 `activating`）。用 `ss -tlnp | grep :7000` 找出佔埠 PID kill 掉，服務即自動接手
- 手動啟動（僅除錯用，用完要 kill）：
```bash
cd /opt/BeakPlatform-dev
source venv/bin/activate
set -a && source .env && set +a
cd backend && flask run --host=127.0.0.1 --port=7000
```
- 對外經 nginx `192.168.0.16:7000/beakplatform` 反代，flask 只綁 127.0.0.1

### 檔案輸出
- **輸出目錄**: `/mnt/smb`（SMB 共享）
- Windows 路徑: `\\192.168.0.16\smb`

---

*最後更新: 2026-03-27*
