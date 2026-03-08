# BeakPlatform CSS/JS 資源盤點與統一檢查表

> 建立日期: 2026-03-08
> 最後更新: 2026-03-08
> 目的: 追蹤 CSS 風格統一進度，避免重複檢查

---

## 全程排除項目

以下三個頁面因第三方套件耦合度極高、獨立模板結構複雜，**本次風格統一任務全程排除**：

| 排除頁面 | URL 路徑 | 模板 | 排除原因 |
|----------|----------|------|----------|
| 表單中心 | `/forms/center` | form_center.html | Formio 深度整合，CSS 高度客製 |
| 流程設計器 | `/api/workflows/designer/standalone` | workflow_designer.html | Cytoscape + Formio，獨立模板 |
| 表單設計器 | `/api/forms/designer/standalone` | form_designer.html | Formio 完整載入，獨立模板 |

相關的 CSS/JS 也排除（不動、不統一）：
- `workflow-designer.css` (48K)、`workflow-main.js` (730K)
- `form-designer.css`、`form-designer-main.js` (69K)
- `form-center.css`、`form-center.js` (73K)
- 所有 Formio/Cytoscape vendor 檔案

### 資安要求：公開頁面 JS 管制

**所有登入頁面及 public 公開區域，絕對禁止載入第三方套件 JS。**
- 若有自行開發的 JS 必須在此文件中逐一註明用途
- JS 是資安漏洞的常見載體，公開頁面暴露面最大
- 違反此規則視為 P0 資安缺陷

**現況審計結果（2026-03-08）**：全部合格，零 JS。
- auth/*.html（登入/忘記密碼/重設密碼）-- 零 JS
- public/*.html（公開首頁/關於）-- 零 JS
- errors/*.html（400/401/403/404/500）-- 零 JS
- 唯一例外：`/dev/quick-login` 載入 Alpine.js + quick-login.js（內網 IP 限制保護）

---

## 一、架構總覽（已更新）

```
載入順序 (base.html 繼承鏈):
  1. Alpine.js (defer)           ← vendor/alpine.min.js (3.14.3)
  2. Remix Icon                  ← fonts/remixicon/remixicon.css
  3. common.css                  ← css/common.css (CSS 變數 + 統一元件)
  4. base-layout.css             ← css/base-layout.css (navbar/menubar/layout)
  5. {% block head %}            ← 各頁面載入專屬 CSS/JS
  6. {% block scripts %}         ← 少數頁面使用

portal_base.html 繼承鏈:
  1. portal.css                  ← css/portal.css (DEV portal 暗色主題)

獨立模板 (不繼承 base.html):
  - auth/*.html (5個)            ← 零 JS、內嵌 CSS
  - errors/*.html (5個)          ← 極簡頁面
  - form_designer.html           ← 排除
  - workflow_designer.html       ← 排除
```

---

## 二、第三方套件清冊

### 全域載入 (base.html)

| 套件 | CSS | JS | 版本 | 用途 |
|------|-----|----|----- |------|
| Alpine.js | - | `vendor/alpine.min.js` (44K) | 3.14.3 | 反應式框架 |
| Remix Icon | `fonts/remixicon/remixicon.css` (136K) | - | - | 主要圖示字型 |

### 按需載入

| 套件 | CSS | JS | 版本 | 使用頁面 |
|------|-----|----|----- |----------|
| Bootstrap | `vendor/bootstrap.min.css` (228K) | `vendor/bootstrap.bundle.min.js` (79K) | 5.3.2 | workflow_list.html (模組層) |
| jQuery | - | `vendor/jquery.min.js` (77K) | 3.7.x | jsTree 依賴 |
| Font Awesome | `vendor/fontawesome/css/all.min.css` (74K) | ~~已刪除~~ | 6.x | quick_login.html (dev) |
| jsTree | `vendor/jstree/.../style.min.css` (27K) | `vendor/jstree.min.js` (139K) | 3.3.16 | 部門/群組樹 |
| Ace Editor | - | `vendor/ace/*.js` (578K) | - | 程式碼編輯器 |
| GridStack | `vendor/gridstack.min.css` (3.6K) | `vendor/gridstack-all.js` (81K) | - | data_crud studio/lab |
| Wunderbaum | `vendor/wunderbaum.css` (22K) | `vendor/wunderbaum.umd.min.js` (97K) | - | data_crud studio |
| Cytoscape | - | `vendor/cytoscape.min.js` (353K) | - | 排除 (workflow_designer) |
| Formio | `vendor/formio.full.min.css` (130K) | `vendor/formio.full.min.js` (1.6M) | - | 排除 (form/workflow designer) |
| Tree (自製) | `vendor/tree/tree.css` (5.5K) | `vendor/tree/*.js` (65K) | - | 部門/組織樹 |
| TreeGrid (自製) | `vendor/treegrid/treegrid.css` (15K) | `vendor/treegrid/*.js` (61K) | - | 群組等 |

---

## 三、CSS 檔案清冊

### 全域共用

| 檔案 | 用途 | 狀態 |
|------|------|------|
| `css/common.css` | CSS 變數 + 統一元件 (btn/table/form/modal/toast/alert/badge) | 已重建 |
| `css/base-layout.css` | 從 base.html 抽離的 navbar/menubar/layout | 新建 |
| `css/portal.css` | 從 portal_base.html 抽離的 DEV portal 暗色主題 | 新建 |

### 平台層頁面專屬

| 檔案 | 用途 | 狀態 |
|------|------|------|
| `css/job-titles.css` | 職稱列表頁面專用 (family-header/supervisor-badge) | 新建 |
| `css/approval-limits.css` | 簽核限額 | 保留 (有自己的 .matrix-table) |
| `css/external-user-edit.css` | 外部人員編輯 | 保留 |
| `css/holidays.css` | 假期設定（日曆/圖例） | 已裁剪 (150→122行) |
| `css/hostconfig-index.css` | 主機設定 | 保留 (75% 唯一佈局) |
| `css/job-matrix.css` | 職等矩陣 | 保留 (特殊佈局) |
| `css/menu.css` | 選單管理（權限著色系統） | 保留 (75% 唯一，核心功能) |
| `css/module-permissions.css` | 模組權限 | 保留 (有自己的 .mp-* 體系) |
| `css/numbering-edit.css` | 編號規則編輯（元素/預覽） | 已裁剪 (156→134行) |
| `css/org-admin-create.css` | 企業管理員建立（email佈局） | 已裁剪 (25→16行) |
| `css/org-admin-rescue.css` | 企業管理員救援（重設密碼） | 已裁剪 (130→22行) |
| ~~`css/org-admins.css`~~ | ~~企業管理員列表~~ | 已刪除 (100% 重複) |
| `css/org-databases.css` | 組織資料庫（master-detail） | 保留 (60% 唯一) |
| `css/org-tree.css` | 組織/部門/群組樹 | 保留 (樹狀結構專用) |
| `css/organizations.css` | 組織列表（Outlook佈局） | 已裁剪 (418→296行) |
| `css/quick-login.css` | 快速登入 (dev) | 保留 |
| `css/schedules.css` | 排程設定（週間工時） | 已裁剪 (100→70行) |
| `css/settings.css` | 系統設定（左側選單） | 保留 (75% 唯一) |
| `css/system-settings.css` | 主機系統設定（設定卡片/頻道） | 已裁剪 (376→223行) |
| `css/user-form.css` | 使用者表單（部門選擇器） | 已裁剪 (230→218行) |
| `css/user-view.css` | 使用者檢視（狀態/操作） | 已裁剪 (62→49行) |

### 孤立/僅排除項目使用

| 檔案 | 說明 | 狀態 |
|------|------|------|
| ~~`css/app.css`~~ | ~~無任何模板引用~~ | 已刪除 (孤立) |
| `css/themes.css` | 僅 workflow_designer.html (排除) | 排除項目專用 |
| `css/theme-styles.css` | 僅 form_designer.html (排除) | 排除項目專用 |

### 模組層

| 模組 | CSS 體系 | 狀態 |
|------|----------|------|
| form_workflow | `fw-*` 前綴 (fw-btn/fw-table/fw-form-group) | 內部一致，不改命名 |
| data_crud | `dc-*` 前綴 (dc-btn/dc-table/dc-form-group) | 內部一致，不改命名 |

---

## 四、已知問題與優先任務

### P0 - 結構性問題

| # | 問題 | 說明 | 狀態 |
|---|------|------|------|
| P0-1 | base.html 內嵌 CSS ~120 行 | 已抽為 `css/base-layout.css` | 完成 |
| P0-2 | portal_base.html 內嵌 CSS ~55 行 | 已抽為 `css/portal.css` | 完成 |
| P0-3 | Font Awesome 冗餘檔案 | 從 17MB 清理至 344KB (css/all.min.css + webfonts/) | 完成 |
| P0-4 | Font Awesome JS 未使用 | JS 目錄已刪除，無任何模板引用 | 完成 |

### P1 - 風格統一

| # | 問題 | 說明 | 狀態 |
|---|------|------|------|
| P1-1 | 按鈕樣式統一 | common.css 定義 .btn 系列，平台層 ~59 頁已套用 | 完成 |
| P1-2 | 表格樣式統一 | common.css 定義 .data-table/.info-table，平台層已套用 | 完成 |
| P1-3 | 表單元素統一 | common.css 定義 .form-control/.form-label/.form-group | 完成 |
| P1-4 | 內嵌 `<style>` 清理 | 平台層高優先頁面已處理 | 完成 |
| P1-5 | 文字色/間距統一 | 平台層已批量 inline → class (.text-muted/.text-danger 等) | 完成 |
| P1-6 | 頁面 CSS 重複定義清理 | 9 個 CSS 檔裁剪 + 2 個刪除，削減 ~522 行重複 | 完成 |

### P2 - 技術債

| # | 問題 | 說明 | 狀態 |
|---|------|------|------|
| P2-1 | 多套樹狀元件共存 | jsTree/Wunderbaum/Tree/TreeGrid 各有用途，暫不收斂 | 評估中 |
| P2-2 | ~~workflow-main.js 730K~~ | ~~拆分~~ | 排除 |
| P2-3 | Bootstrap 非全域 | 僅 workflow_list.html 使用 | 評估中 |
| P2-4 | 獨立模板一致性 | auth/error 零 JS，designer 已排除 | 不需處理 |
| P2-5 | DevTools CDN 引用 | 已改用主應用 static 目錄 | 完成 |

---

## 五、完成進度總覽

### 第一階段: 建立基礎 -- 完成

- [x] base.html 內嵌 CSS 抽為 `base-layout.css` (193行 -> 73行)
- [x] common.css 重建：CSS 變數色票 + 統一元件 (btn/table/form/modal/toast/alert/badge/工具類)
- [x] 新增 `.data-table` (含 .compact/.bordered), `.info-table`, `.page-header`, `.page-title`

### 第二階段: 清理冗餘 -- 完成

- [x] Font Awesome 清理 (17MB -> 344KB)
- [x] DevTools CDN → 本地路徑
- [x] portal_base.html 內嵌 CSS 抽為 `portal.css`

### 第三階段: 逐頁統一 -- 平台層完成

已處理約 59 個平台層模板：
- [x] 高優先 4 頁 (job_titles/list, change_password, roles/list, roles/edit)
- [x] 中優先 13 頁 (delegations, sys_accounts, users, organizations 等)
- [x] 低優先 42 頁 (CRUD 批量處理)

主要變更：
- 裸 `<table border="1">` → `.data-table.bordered`
- 裸 `<table border="0">` (表單佈局) → `.info-table`
- inline button style → `.btn .btn-primary/danger/warning`
- inline color → `.text-muted/.text-danger/.text-success`
- 表頭 inline background → 移除

### 第四階段: 頁面 CSS 重複裁剪 -- 完成

已處理 14 個頁面專屬 CSS 檔案，移除與 common.css 重複的定義：
- [x] 刪除 `org-admins.css` (100% 重複)、`app.css` (孤立)
- [x] 裁剪 9 個 CSS 檔：移除重複的 btn/modal/form-group/badge/message 定義
- [x] 硬編碼色值轉 CSS 變數 (如 `#0066cc` → `var(--color-primary)`)
- [x] common.css 新增 `.modal-close`、`.btn-reset-pwd`、`.message` / `.message-success` / `.message-error`
- [x] 3 個 admin 模板 inline styles → common.css 類別
- [x] holidays/schedules 模板 `.holidays-table/.schedules-table` → `.data-table`
- [x] numbering 模板按鈕加 `.btn` 基底類

### 保留不動的頁面 CSS（已為最終狀態）

| 檔案 | 保留原因 |
|------|----------|
| `css/hostconfig-index.css` | 工具卡片佈局，75% 唯一 |
| `css/menu.css` | 權限等級著色系統，核心功能 |
| `css/org-databases.css` | master-detail 佈局，60% 唯一 |
| `css/settings.css` | 左側設定選單，75% 唯一 |
| `css/approval-limits.css` | 簽核矩陣表格 |
| `css/external-user-edit.css` | 外部人員編輯 |
| `css/job-matrix.css` | 職等矩陣佈局 |
| `css/module-permissions.css` | `.mp-*` 獨立體系 |
| `css/org-tree.css` | 樹狀結構專用 |
| `css/quick-login.css` | 開發用快速登入 |
| data_crud 模組 | `dc-*` 體系，不改 |
| form_workflow 模組 | `fw-*` 體系，不改 |
| auth/error 模板 | 零 JS，極簡，不需處理 |

---

## 六、common.css 統一元件速查

```
CSS 變數:  --color-primary (#0066cc), --color-danger, --color-success, --color-warning, --color-info
           --color-text, --color-text-secondary, --color-text-muted
           --color-border, --color-border-light, --color-bg, --color-bg-light
           --border-radius (4px), --font-size-base (14px), --font-size-sm (13px)

按鈕:      .btn .btn-primary/secondary/danger/success/warning/cancel/sm/link
表格:      .data-table (.compact, .bordered), .info-table
表單:      .form-control, .form-label, .form-group, .form-row
頁面:      .page-header, .page-title, .page-actions
區段:      .section-title (.optional)
Modal:     .modal-overlay, .modal-box, .modal-content, .modal-header/body/footer, .modal-close
Toast:     .toast (.success/.error/.warning/.info)
Alert:     .alert (.alert-success/.alert-error/.alert-warning/.alert-info)
           .message (.message-success/.message-error) — hostconfig/organizations 別名
Badge:     .badge (.badge-success/.badge-warning/.badge-danger/.badge-info/.badge-secondary)
密碼:      .password-field, .btn-toggle, .btn-generate, .btn-reset-pwd
工具:      .text-muted/danger/success/warning/center/right/left/nowrap
           .mt-0/8/16, .mb-0/8/16, .hidden
```

---

## 七、JS 套件用途速查

| 套件 | 用途 | 依賴 CSS | 備註 |
|------|------|----------|------|
| Alpine.js 3.14.3 | 所有頁面的反應式框架 | 無 | 全域 defer 載入 |
| Bootstrap 5.3.2 | UI 元件 | bootstrap.min.css | 僅 workflow_list.html |
| jQuery 3.7.x | jsTree 依賴 | 無 | 僅 jsTree 頁面 |
| Cytoscape | 流程圖 | 無 | 排除 (workflow_designer) |
| Formio | 動態表單 | formio.full.min.css | 排除 (designer) |
| jsTree 3.3.16 | 樹狀結構 | jstree style.min.css | 部門/群組 |
| Ace Editor | 程式碼編輯器 | 無 | JSON/JS/HTML/CSS |
| GridStack | 拖放格線佈局 | gridstack.min.css | data_crud studio/lab |
| Wunderbaum | 進階樹狀檢視 | wunderbaum.css | data_crud studio |
| Tree (自製) | 組織/部門樹 | tree.css | 新實作 |
| TreeGrid (自製) | 樹狀表格 | treegrid.css | 群組等 |
| Font Awesome 6.x | 圖示 (CSS only) | all.min.css | 僅 quick_login (dev) |
| Remix Icon | 圖示字型 | remixicon.css | 全域，主要圖示來源 |

---

*本文件由 CSS/JS 全面盤點產生，作為統一工作的追蹤基準。*
