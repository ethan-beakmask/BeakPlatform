# BeakPlatform - Claude Code 專案規範

## 這份文件的範圍（2026-07-29 重整）

本檔只放**「不知道就會做錯」的規範與環境事實**。細節與可重複使用的內容已分流：

| 找什麼 | 去哪 |
|---|---|
| 派工給 codex 時要貼的規範片段 | **`docs/codex_spec/`**（frontend / i18n / security / portal / _footer） |
| 檔案上傳下載的完整 API 用法 | `docs/FILE_SERVICE.md` |
| 改哪些檔案（工單導向） | `docs/manifests/README.yaml` → 對應 manifest |
| 安全踩坑清單 | `docs/manifests/SECURITY_PITFALLS.md` |
| 權限模型定版 | `docs/PERMISSION_MODEL.md`、`docs/COMPONENT_VISIBILITY_GUIDE.md` |
| 名詞對照 | `docs/GLOSSARY.md` |
| 跨 session 待辦與決策脈絡 | BeakBroodNest 知識庫（`note_search` / `note_get`） |

**維護原則**：新的踩坑先問「這是 codex 猜不到的專案特有事實，還是通用工程常識？」
前者才寫進來；屬於「派工時要貼給 codex」的，寫進 `docs/codex_spec/` 並在本檔留指針。

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
- 權限管理 UI 統一入口：`/access/` 權限管理中心（功能授權/角色/帳號配角色/健檢；
  舊 `/permissions/`、`/roles/`、`/admin/account-roles/` 已退役，`/menu/` 只管選單結構）；
  規格 `docs/ACCESS_CENTER_SPEC.md`
- Phase B 起頁面路由**不掛身分 decorator**：url 型選單路徑前綴即 PageRoleGuard 領地；
  單頁專屬資料 API 掛 `@page_keys_required('<menu_code>')`
- Phase D 元件級：動作按鈕一律包 `{% if can('<permission_code>') %}`（JS 用 `BkCaps.can()`），
  對應動作 API 掛 `@permission_required('<permission_code>')`（capability_service）；
  指引 `docs/COMPONENT_VISIBILITY_GUIDE.md`（四層防線總表 + NoCode_Builder 消費規則）

### PERM-02: D2 元件級推廣檢查（強制，2026-07-18 起）

**任何開發或修改工單，凡觸及「頁面模板、動作按鈕（增刪改查/簽核/撤銷等）、動作型 API」，
動工前必須先問用戶：「本次是否依 D2 標準進行？」**，取得答覆後才能實作。

- D2 標準 = 按鈕包 `can()`、動作 API 掛 `@permission_required`、code 沿用 API 層既有
  permission code（詳見 `docs/COMPONENT_VISIBILITY_GUIDE.md` §2.5）
- 用戶答「是」→ 該工單範圍內的按鈕與 API 一併完成 D2 改造；答「否」→ 照原樣修改，不擅自加
- 純資料修正、CSS、i18n、文件等不觸及按鈕/動作 API 的工單不必問
- 全新頁面**不必問，一律直接套 D2 標準**（新程式碼沒有理由用舊模式）

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

**所有檔案操作必須透過 `file_service`，禁止自行實作上傳/下載邏輯。**

- 加密由 `storage_type` 自動決定（`form_attachment` / `subsystem_file` 走 AES-256-GCM），
  程式不需手動呼叫加密函式
- 前端一律用 `BkFileAttachment` 元件，不要自己寫上傳 API 呼叫
- **禁止**繞過 `file_service` 直接讀寫 uploads/ 或 encrypted_storage/
- **禁止**手動呼叫 `crypto/engine.py`
- **禁止**將 `ENCRYPTION_MASTER_KEY` 硬編碼或寫入版控

完整 API 用法、context_type 對應表、金鑰架構：**`docs/FILE_SERVICE.md`**

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

**HTML 模板中禁止大量內嵌 JS/CSS。**

| 類型 | 規範 |
|------|------|
| CSS | 抽為 `.css` 靜態檔 |
| JS 邏輯 | 抽為 `.js` 靜態檔 |
| 膠水碼（初始化、Jinja2 變數注入） | 可留在 HTML，不超過 30 行 |

平台層：`backend/app/static/js|css/`；模組層：`modules/<name>/static/modules/<name>/js|css/`

需要把 Jinja2 變數帶進 JS 時用 window bridge（`window.__PAGE_CONFIG = {...}`）。
JS 與 Jinja2 深度交織無法乾淨分離時，才保留 `{% include "_xxx_methods.html" %}` partial。

抽離模式範例與完整說明：**`docs/codex_spec/frontend.md`**


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

需要唯一識別碼的建立表單，統一 UX：輸入名稱 → debounce 500ms → `POST /api/code/generate`
取得建議值當 placeholder → 手動輸入時 `POST /api/code/validate` 即時驗證 →
留空提交時後端採用建議值。不強制大小寫轉換。

前端引入 `/static/js/code-input.js` 的 `codeInputMixin(entityType)`，
標準區塊 HTML 用 `{% include "partials/_code_input.html" %}`。

### FRONT-05 / FRONT-06 / FRONT-08: 前端框架陷阱

以下三條寫錯會造成排版錯亂或功能靜默失效，**派工給 codex 時必須貼進 prompt**
（完整說明與範例在 `docs/codex_spec/frontend.md`）：

- **FRONT-05**：CSS 全寬規則必須排除 radio/checkbox
  （`input:not([type="radio"]):not([type="checkbox"])`），否則同列文字被擠成直排
- **FRONT-06**：有 `x-show` 的元素禁止 inline style 設 `display`
  （x-show 還原時會清掉，佈局遺失）
- **FRONT-08**：select 綁動態 `x-for` options 時，option 必須加
  `:selected="<值> === <狀態>"`，否則初次渲染顯示第一個選項
  （症狀：一進頁面顯示錯的，手動改一次就正常，極易漏看）


### FRONT-07: 模組 CSS 命名與排版規範

**平台未載入 Bootstrap。** 全域 CSS 只有 `common.css` + `base-layout.css`，
提供 `.btn` / `.data-table` / `.form-control` / `.modal-overlay`，**沒有 Grid 系統**。

- 禁止 `row` / `col-md-*` / `card` / `table-sm` / `mb-3` / `d-flex` 等 Bootstrap class
  （寫了完全無效果，排版會全部擠在一起）
- 排版用 CSS Grid / Flexbox；模組 class 加前綴（`wks-`、`ird-`、`fw-`、`pir-`）

**CSS 變數白名單**（只能用這些，禁止自創）：

```
--color-primary  --color-text  --color-text-secondary  --color-text-muted
--color-bg  --color-bg-white  --color-bg-light  --color-border
```

自創 `--text-primary`、`--surface-color` 這類不存在的變數時，CSS fallback 值會生效，
曾造成整頁深色 fallback、白底白字。**派工給 codex/agent 時必須在 prompt 明列此白名單。**

版型範例：`modules/form_workflow/static/modules/form_workflow/css/fw-dashboard.css`


### FRONT-09: D2 的 `BkCaps.can()` 需要頁面注入 `__PAGE_CAPS`

`capability.js` 的 `BkCaps.can(code)` 讀 `window.__PAGE_CAPS`，
**該變數由各頁面自行注入，沒有全域預設值**。漏注入時 `can()` 恆為 `false`，
症狀是**按鈕點下去完全沒反應、console 也不報錯**。

```python
from app.services.capability_service import build_caps
return render_template('...', page_caps=build_caps(['module.permission_code']))
```
```html
<script>window.__PAGE_CAPS = {{ page_caps | default({}) | tojson }};</script>
```

模板層的 `{% if can('...') %}` 走後端 Jinja2 global，**與此無關**——
所以會出現「按鈕有渲染出來但點了沒用」的矛盾現象，這正是漏注入的特徵。
（`layouts/base.html` 已載入 capability.js，不必重複引入。）


### FRONT-10: 後端組「指向本頁」的網址必須帶 `request.script_root`

app 掛在 nginx 的 `/beakplatform` 前綴下，而 **Flask 的 `request.path` 不含該前綴**。
只用 `request.path` 組出的 `/public/portal/...` 在瀏覽器上會被當成缺前綴的
絕對路徑而 404。

```python
# 錯：點下去 404
f"{request.path}?{urlencode(args)}"
# 對
f"{request.script_root}{request.path}?{urlencode(args)}"
```

Page IR 的排序連結**從第一版起就是壞的**，直到 2026-07-29 才發現
（`renderer._self_url()` 已修）。原因見下條。

### VERIFY-01: 使用者要點擊的東西，驗收必須用瀏覽器

curl 對「連結、按鈕、select 初次渲染值」有**結構性盲區**：

- 用 curl 測連結時都是自己帶完整路徑，永遠測不出網址少了前綴（FRONT-10 的成因）
- select 顯示錯值（FRONT-08）在 HTML 原始碼裡看不出來，要渲染後才知道
- `BkCaps.can()` 漏注入（FRONT-09）的症狀是「按鈕點了沒反應、console 不報錯」

→ 只要變更涉及使用者要點的東西，curl 驗完**還要**用 chrome-devtools 實際點一次。

### VERIFY-02: 驗收輸出必須留證（2026-08-01 起）

**驗收的原始輸出一律落地到 `/opt/tmp/verify/<日期>-<主題>.log`，不要只留在對話裡。**

```bash
mkdir -p /opt/tmp/verify
curl ... 2>&1 | tee -a /opt/tmp/verify/20260801-file-authz.log
../venv/bin/python -m pytest tests/test_xxx.py -q 2>&1 | tee -a /opt/tmp/verify/20260801-file-authz.log
```

瀏覽器驗收同理：chrome-devtools 的截圖存檔、關鍵 console/network 觀察貼進同一個 log。

**理由**：2026-08-01 對四個 session 做事後幻覺稽核（363 條事實斷言逐條查證，見知識庫 #4957），
41 條判定為 UNVERIFIABLE——絕大多數是瀏覽器實測與 rate-limit 觀察，**輸出當下就沒落地，
事後無論花多少成本都查不回來**。「我測過了」若沒有留下輸出，事後與「我以為我測過了」無法區分。
留證的成本是一個 `tee`，缺證的成本是整段驗收失去可覆核性。

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

平台支援 zh-TW（原文即 key）+ en。**所有新 user-facing 字串必須包翻譯函式**：
Python `_('中文')`、Jinja2 `{{ _('中文') }}`、JS `__('中文')`。

**四條地雷**（違反會 500 或讓功能失效）：
- msgid 含字面 `%` 必須寫 `%%`（flask_babel 一律做 % 插值）
- **禁止**包裹參與 `==`/`===` 比較的字串與機器可讀錯誤碼（包了前端比對即失效）
- **禁止**包裹 logger/console 訊息、寫入 DB 的資料值、email 主旨內文
- pybabel update 的 fuzzy 配對幾乎全錯，必須逐條重翻並清 fuzzy flag

**extract 必須帶齊全部已包裹模組目錄**（open_defense / vuln_lifecycle / spec_formulate /
nocode_builder / form_workflow）——少帶任何一個，該模組 msgid 會被打成 obsolete
並喪失翻譯（已發生過事故）。新模組包裹後要加進清單。

完整指令、JS 字典規則、FormIO locale 陷阱：**`docs/codex_spec/i18n.md`**
進度計畫：`docs/I18N_PLAN.md`


## 時區處理規範 (TZ-01)

**DB 一律存 UTC**（`datetime.utcnow()`，欄位 `timestamp without time zone`）。
純日期欄位（`effective_from`、合約日期）不涉及時區，直接存日曆日期。

顯示時區優先序由 `auth_interceptor.py` 設定：**用戶個人 > 企業設定 > `Asia/Taipei`**（`g.timezone`）。

| 位置 | 必須 | 禁止 |
|---|---|---|
| 後端模板 | `{{ dt\|tz_format('%Y-%m-%d %H:%M') }}` | `dt.strftime()`（會顯示 UTC） |
| 前端 JS | `BkTime.format(dateStr, 'short')` | `new Date(x).toLocaleString()`（會用瀏覽器時區） |
| 後端 API 回格式化字串 | 先 `.replace(tzinfo=UTC).astimezone(user_tz)` 再 strftime | 直接 strftime |

`BkTime` 由 `timezone.js` 在 base.html 全域載入，style 可用 `full`/`short`/`date`/`time`。

**自行做時間運算時（SLA 倒數、時間差）**：DB 回的 ISO 字串是 naive UTC（無 `Z` 後綴），
直接 `new Date(iso)` 會被當本地時間、差 8 小時（已踩過：SLA 顯示逾時 465 分）：

```javascript
const iso = s.endsWith('Z') ? s : s + 'Z';   // naive UTC 補 Z
const deadline = new Date(iso).getTime() + slaMinutes * 60000;
```


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
15. **禁止** select 綁動態 `x-for` options 卻不加 `:selected`（初次渲染會顯示錯值，參見 FRONT-05/06 段）

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
- curl 快速切換**任意帳號**（免密碼免 CSRF，POST JSON 版，E2E 多帳號矩陣測試首選）:
  ```bash
  USC=$(psql -h localhost -U beakplatform -d beakplatform_dev -t -A \
    -c "SELECT secure_code FROM users WHERE email='ethan@lion.com' AND is_deleted=false;")
  curl -s -c cj.txt -X POST "$BASE/dev/quick-login" \
    -H 'Content-Type: application/json' -d "{\"user_id\":\"$USC\"}"
  ```
- 常用 API 回應格式備忘：`GET /api/menu` 回 `{menu:[...]}`（樹狀，key 是 `menu` 不是 items）；
  權限中央 API（/api/permissions/*）的企業參數名是 `org_code`（不是 org）
- curl 打非 exempt 的 POST API 需要 CSRF token，從任一登入後頁面的 meta 取（登入回應不含 token）：
  ```bash
  TOKEN=$(curl -s -b cj.txt -c cj.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
  curl -s -b cj.txt -X POST "$BASE/api/xxx" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" -d '{...}'
  ```

### NoCode Builder / Portal 開發備忘（2026-07-28 起）

**架構原則（2026-08-03 用戶定案，違反者不是 bug 是架構錯誤）**：

- NoCode 子系統的資料**自給自足**。要與平台交換一律是**平台寫入、平台去讀**，
  不從 SQLite / NoCode 側取用平台資料（流程元件取資料算平台本身的功能，不在此限）。
  目的有二：把 NoCode 側的 SQL injection 受害範圍鎖在 SQLite 內攻不進平台；
  以及保持 **NoCode 本來就能獨立成單一專案**的可分離性（整合進 BeakPlatform 是產品策略）
- 因此 `registry.get_resource()` 在 portal 語境對無 prefix 的平台資源一律回 None
  （`backend/app/pageir/registry.py:46-47`）**是這條原則的實作，不要放寬**。
  症狀會是 `PageIrRenderError: Unregistered resource: user` → 422，
  正解是把頁面改綁 `portal:` / `formflow:` 資源，不是去改 registry
- **所有 nocode 子系統頁面一律以 portal 方式渲染**（員工也一樣，只是身分來源不同），
  平台端不存在「nocode 頁面」。故 `_ACTIONS`（平台側動作白名單）永遠是 0 筆，
  那是預期狀態不是待補項

**兩個帳號世界完全分離**，測試時 cookie jar 要分開（同一個 jar 也能並存，但別混淆）：

| | 平台世界 | Portal 世界 |
|---|---|---|
| 入口 | `/nocode/workspace/<sub_system_sc>`（統一工作區） | `/public/portal/<path_id>/...` |
| 帳號 | PostgreSQL `users` | 子系統 SQLite `portal.db` 的 `portal_users` |
| session | Flask-Login | `session['portal_sessions'][sub_sc]`（per 子系統並存） |
| 渲染語境 | `platform` | `portal`（互斥，跨界解析一律 fail-closed） |

```bash
# portal 帳號登入（表單 POST，非 JSON；用獨立 cookie jar）
curl -s -c p4_cj.txt -X POST "$BASE/public/portal/<path_id>/login" \
  -d 'username=<帳號>&password=<密碼>'

# portal 頁的 CSRF token 在頁面 meta（平台的 /dashboard 取不到 portal 用的）
TOKEN=$(curl -s -b p4_cj.txt "$BASE/public/portal/<path_id>/p/<page_sc>" \
  | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)

# 子系統 SQLite 直查（portal.db=帳號/群組/階級，portal_data.db=業務資料）
sqlite3 /opt/BeakPlatform-dev/data/nocode_portals/<sub_system_sc>/portal.db \
  "SELECT username, group_code, level_code FROM portal_users;"
```

- `path_id` 不等於 `sub_system_sc`，對照在 `lookup_items.value_str`：
  `SELECT code, value_str FROM lookup_items WHERE value_str='<sub_system_sc>';`
- **Page IR 設計器網址是 `/nocode/ir-designer/<page_layout_secure_code>`**
  （預覽是同路徑 `+ /preview`）。它吃的是**頁面** secure_code，不是子系統 sc，
  路由定義在 `modules/nocode_builder/web/__init__.py:42`
- **portal 頁是獨立模板 `portal_page_v3.html`，不繼承 `layouts/base.html`**。
  平台頁自動有的東西（`timezone.js`／`BkTime`、i18n、capability.js）在這裡
  **都要自己載入**。portal 又是公開路由，`auth_interceptor` 在設定
  `g.locale` / `g.timezone` 之前就 return 了，所以時區一律吃 fallback `Asia/Taipei`
- **這條對 portal 的錯誤頁與任何新增 portal 模板一律適用**，不只主頁。
  錯誤路徑最容易漏：`pageir/page_error.html` 繼承了 `layouts/base.html`，
  被 portal 端共用了很久，導致 portal 渲染失敗時**外部訪客拿到帶平台
  navbar／選單／`capability.js` 的頁面**（2026-08-03 commit `853b5aaf` 修，
  改用 `modules/nocode_builder/portal_page_error.html`）。
  **新增任何 portal 端要用的模板前，先確認它沒有 `{% extends "layouts/base.html" %}`。**
  平台世界的 `/p/` 與純平台預覽仍用原本的平台版錯誤頁，那是正確的
- **在 Page IR 頁面放 form.io 送出按鈕時必須寫 `"input": false`**，
  否則 payload 會多一個 `submit: true` 欄位，被後端欄位白名單擋成
  400 `unknown_field`
- **portal 業務表有列級擁有權**（2026-07-30 起）：表固定有系統欄位 `portal_user_ref`
  （值 `u:<portal user_id>` / `g:<guest_token>`），視圖 `DcCrudView.row_owner_scope`
  預設 **`own`**（只能存取自己建的列），要共享的表必須明確設 `all`。
  `portal_user_ref IS NULL` 的舊列在 own 模式下誰都看不到——
  **「portal 頁表格突然空了」第一個要查的就是這個**，不是權限判定壞了。
  既有表補欄位用 `scripts/add_portal_user_ref.py --apply`（冪等）。
  細節與 `owner_ref` 傳參規則見 `docs/codex_spec/portal.md`
- **判斷一個 NoCode 頁面「還活著」必須走雙路徑 OR**，只看 site map 會誤判：
  ```
  存活 = (有存活 dc_site_map_nodes 指向 且 該節點的子系統存活)
      OR (有存活 dc_sub_system_pages 掛載 且 該子系統存活)
  ```
  portal 頁**不一定掛在 site map 節點下**，可能只透過 `dc_sub_system_pages` 關聯
  （`FORMTEST00000000000001`、`qiHMpMCul-1KGxhU4Q7Trd` 就是這種）。
  2026-07-31 清孤兒時只看 site map，把這兩個 published 驗收頁誤刪，
  其中前者是 `test_e2e_portal_cancel.py` 的依賴，**刪掉會讓 E2E 靜默 skip 而不是報錯**。
  此判定的**唯一實作**是
  `modules/nocode_builder/services/page_ownership_service.py`
  （`is_page_reachable()` / `get_owner_sub_system_codes()`），
  存取層、刪除級聯、清理腳本共用，**禁止各自重寫**。
  注意 `is_page_reachable()` 對「零關聯」回 `True`（純平台 IR 頁要放行），
  所以判斷「該不該刪這個頁」時條件要寫成
  `not is_page_reachable(sc) or not get_owner_sub_system_codes(sc)`。
  既有孤兒用 `scripts/cleanup_orphan_nocode_pages.py --dry-run/--apply`（冪等）清。
- **建立子系統會自動附贈一個 welcome 節點 + welcome 頁面**，
  且 **site map 只允許一個根頁面**（再建根節點會回 400
  「Site Map 只能有一個根頁面 (welcome)」，新節點要指定 `parent_secure_code`）。
  測級聯或建測試資料時會撞到。
- 權限判定失敗**一律回 404**（不洩漏存在與否）；查原因看
  `sudo journalctl -u beakplatform-dev.service --since "-5 min" | grep reason=`
- 權限模型與判定鏈：`docs/PORTAL_ACCOUNT_SPEC.md`；
  完整交接與踩坑清單：`docs/handoff_nocode_n1_n5.md`
- v2 `layout_json` 已退役，`/p/` 遇到會回 410；設計器只認 `ir_version: 3`

### pytest 既有環境問題（不要試圖修）

跑完整 `pytest tests/` 會有 **13 個 error**，原因是測試 app 用 SQLite `db.create_all()`
但平台有 PostgreSQL `JSONB` 欄位（最早卡在 `menu_defaults.title_i18n`），
與任何功能變更無關。**驗收時只跑相關測試檔**，或以這 13 個為基準線比對是否退步：

```bash
cd /opt/BeakPlatform-dev/backend
../venv/bin/python -m pytest tests/test_pageir_*.py tests/test_portal_*.py \
  tests/test_sitemap_access_matrix.py tests/test_platform_fixed_filters.py -q
# 基準 248 passed（2026-07-30）
```

**`tests/test_e2e_portal_cancel.py` 刻意不在基準清單內**（掛 `pytest.mark.e2e`，
需要本機實跑服務 + PostgreSQL，服務沒起來會 skip）。要跑它就單獨跑：
`../venv/bin/python -m pytest tests/test_e2e_portal_cancel.py -q`

### form_workflow 發行（publish）陷阱
- `POST /api/mappings/<sc>/publish` 以表單/流程模板的 **version+revision** 判斷有無變更；
  直接改 `fw_workflow_templates.graph`（SQL 或 PUT API）**不會** bump revision，
  publish 會回「版本未變更」並沿用舊快照
- 解法：改完 graph 先 `UPDATE fw_workflow_templates SET revision = revision+1 WHERE ...` 再 publish
- intake / 表單中心都只讀 `fw_published_form_workflows` 最新 Published 快照，改模板不重發行等於沒改
- 流程變數：流程編號（OD-YYYYMMDD-NNNN）是 `${wi.exec_code}`；`${wi.code}` 是 workflow instance 的 secure_code，
  沒有 `${wi.execution_code}` 這個變數（替換結果為空字串）

### form_workflow 流程變數的儲存位置（寫錯地方＝流程引用不到）

**流程變數的權威儲存是 `fw_workflow_variables` 表，不是
`fw_workflow_instances.variables` JSONB。**

- `${v.xxx}` 走 `VariableService`，**只讀那張表**
- `${wi.xxx}` 只支援五個欄位（`base.py` 的
  `_WI_FIELDS = {'wi.code','wi.exec_code','wi.name','wi.status','wi.depth'}`）
- **兩條路都到不了 `variables` JSONB** —— 寫進 JSONB 只有自己查得到，
  流程設計者引用不到。要讓流程引用得到就用
  `VariableService.set_flow_var(instance_code, name, value, org_code)`
- 流程設計者設變數用既有的 **`OpSet`（設定變數）節點**

**`VariableService._cache` 是類別層級、無 TTL 的進程內快取。**
開發環境是 `flask run` 單進程 + 同進程 daemon thread 跑流程引擎，看不出問題；
多 worker 部署下，流程改了變數之後其他 worker 仍讀到舊值。
**用過期值做顯示只是難看，用過期值做授權判定就是漏洞** ——
授權判定一律繞過快取直接查 `FwWorkflowVariable`
（範例：`pageir_formflow_resources.is_submission_editable()`）。

### 服務啟動
- **正式管道是 systemd 服務**：`sudo systemctl restart beakplatform-dev.service`（重啟後 `systemctl is-active` 確認）
- 開發服務以**非 debug 模式**跑，Python/模板變更**不會自動重載，必須重啟**
- **踩坑**：若曾手動 `flask run`，殘留進程會佔住 7000 埠導致 systemd 服務 crash loop（`is-active` 一直是 `activating`）。用 `ss -tlnp | grep :7000` 找出佔埠 PID kill 掉，服務即自動接手
- **flask CLI 必須先載入 .env**（缺 SECRET_KEY 直接 ValueError）：
  ```bash
  cd /opt/BeakPlatform-dev && set -a && source .env && set +a
  cd backend && ../venv/bin/flask module sync --force   # 同步模組選單/權限定義到 DB
  ```
  模組選單的 user_types 改在模組 `__init__.py` 定義後需跑此指令；啟動時的自動同步**不含**權限覆寫（僅 --force 才會）
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
