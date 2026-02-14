# 前端整理進度追蹤 (HTML 瘦身)

> 目標：所有模板符合 FRONT-01/02 規範（500 行上限，無大段內嵌 JS/CSS）

## 狀態說明
- [x] 已完成
- [ ] 待處理
- [-] 進行中

---

## Phase 0: 基礎建設
- [x] `backend/app/static/css/common.css` — 共用樣式（[x-cloak], .section-title, .modal-overlay, .toast, .form-row）
- [x] `layouts/base.html` — 加入 common.css 引用
- [x] `docs/FRONTEND_CLEANUP_CHECKLIST.md` — 本文件
- [x] 關閉 Forgejo Issue #11（Bulma CSS 風格統一化已無需進行）

## Phase 1: 快速勝利（零 Jinja2 耦合）
| 模板 | 原始行數 | 瘦身後行數 | CSS 檔 | JS 檔 | 狀態 |
|------|----------|-----------|--------|-------|------|
| `template_list.html` | 700 | 244 | `template-list.css` | `template-list.js` | [x] |
| `workflow_list.html` | 674 | 296 | `workflow-list.css` | `workflow-list.js` | [x] |

## Phase 2: 中等難度（少量 Jinja2，Window Bridge）
| 模板 | 原始行數 | 瘦身後行數 | CSS 檔 | JS 檔 | 狀態 |
|------|----------|-----------|--------|-------|------|
| `holidays.html` | 1011 | 205 | `holidays.css` | `holidays.js` | [x] |
| `schedules.html` | 905 | 226 | `schedules.css` | `schedules.js` | [x] |
| `form_center.html` | 1880 | 393 | `form-center.css` | `form-center.js` | [x] |
| `form_designer.html` | 479 (含4 partial 共1938) | 133 | — (已有) | `form-designer-main.js` | [x] |

### Phase 2 額外產出
- `_form_center_list_view.html` — 表單中心清單模式 partial (~307 行)
- `_form_center_approval_modal.html` — 表單中心簽核模態框 partial (~117 行)
- 已刪除: `_monitor_methods.html`, `_read_form_methods.html` (合併入 form-center.js)
- 已刪除: `_designer_toast_init.html`, `_designer_background.html`, `_designer_preview_print.html`, `_designer_save_template.html` (合併入 form-designer-main.js)

## Phase 3: 高難度（多 Jinja2，需解耦）
| 模板 | 原始行數 | 瘦身後行數 | CSS 檔 | JS 檔 | 狀態 |
|------|----------|-----------|--------|-------|------|
| `groups.html` | 1305 | 238 | `org-tree.css` (共用) | `groups.js` | [x] |
| `users/create.html` | 930 | 256 | `user-form.css` | `user-form.js` | [x] |
| `departments.html` | 351 (含 393 行 CSS partial) | 351 | `org-tree.css` (共用) | — (保留 partial) | [x] |

### Phase 3 額外產出
- `org-tree.css` (467 行) — 部門/社群共用樣式（tree-panel, jstree, staff-layout, 拖放等）
- 已刪除: `_departments_styles.html` (搬入 org-tree.css)

## Phase 4: 批量處理剩餘 HIGH 檔案

### 超過 500 行（已完成）
| 模板 | 原始行數 | 瘦身後行數 | CSS 檔 | JS 檔 | 狀態 |
|------|----------|-----------|--------|-------|------|
| `users/edit.html` | 600 | 361 | `user-form.css` (共用) | `user-edit.js` | [x] |
| `mappings_list.html` | 623 | 276 | `mappings.css` | `mappings.js` | [x] |
| `dev/quick_login.html` | 709 | 215 | `quick-login.css` | `quick-login.js` | [x] |
| `admin/settings.html` | 640 | 319 | `settings.css` | `settings.js` | [x] |

### 500 行以下（已完成）
| 模板 | 原始行數 | 瘦身後行數 | CSS 檔 | JS 檔 | 狀態 |
|------|----------|-----------|--------|-------|------|
| `users/view.html` | 497 | 220 | `user-view.css` | `user-view.js` | [x] |
| `numbering/edit.html` | 451 | 290 | `numbering-edit.css` | — (23 行 Jinja2 留 inline) | [x] |
| `org-admins/list.html` | 391 | 162 | `org-admins.css` | `org-admins.js` | [x] |
| `category_list.html` | 379 | 164 | `category-list.css` | `category-list.js` | [x] |

> 以下檔案已不存在（已從專案移除或改名），從清單移除：
> `job_levels/matrix.html`, `external-users/edit.html`, `roles/create.html`,
> `pending_list.html`, `roles/edit.html`, `dashboard.html`

### Phase 4 額外產出
- `user-form.css` 新增編輯頁面特有樣式（edit-form, readonly-info, btn-row, danger-zone, readonly-notice）
- `settings.css` + `settings.js` — 系統設定頁（Logo/一般設定/密碼政策/左側選單高亮）
- `user-view.css` + `user-view.js` — 用戶詳情頁（重設密碼）
- `numbering-edit.css` — 編號規則編輯頁（JS 留 inline，僅 23 行含 Jinja2）
- `org-admins.css` + `org-admins.js` — 企業管理員列表（重設密碼）
- `category-list.css` + `category-list.js` — 分類管理頁

## Phase 5: 收尾
- [x] 刪除已轉為外部 .js 的死 partial 檔案 → **審計結果：0 個死 partial**，全部 18 個 partial 都有被引用
- [x] 全模板合規審計（FRONT-01/02）→ Phase 1-4 目標的大型檔案全部完成；剩餘 32 個小型模板有超過 30 行內嵌 CSS/JS，但均 <500 行（除 organizations/list.html 1004 行、workflow_designer.html 1081 行為後續待辦）
- [x] 去重：移除 `app.css` 中重複的 `[x-cloak]`、`user-form.css` 中重複的 `.section-title`
- [x] 更新本文件標記完成

### Phase 5 審計結果
- ~~**超過 500 行**（後續待辦）：`organizations/list.html` (1004 行)、`workflow_designer.html` (1081 行)~~ → Phase 6 已完成
- **密碼模態框 CSS 重複**（後續可優化）：`user-view.css` 和 `org-admins.css` 有高度重複的密碼重設樣式，可抽為共用 class
- **模態框 / 按鈕 CSS 重複**（後續可優化）：`holidays.css`、`schedules.css`、`org-tree.css` 有重複的 `.modal-*` 和 `.btn-*` 定義

## Phase 6: 優先級 1 超限模板處理
| 模板 | 原始行數 | 瘦身後行數 | CSS 檔 | JS 檔 | 狀態 |
|------|----------|-----------|--------|-------|------|
| `organizations/list.html` | 1004 | 309 | `organizations.css` | `organizations.js` (Mode B) | [x] |
| `workflow_designer.html` | 1081 | 845 | 合併至 `workflow-designer.css` | `workflow-designer-init.js` | [x] |

> `workflow_designer.html` 845 行仍超 500，但為獨立頁面（不用 base.html），剩餘均為 HTML 結構（5 個 Tab 面板），已無大段內嵌 JS/CSS。如需進一步瘦身需拆 HTML partial。

### Phase 6 額外產出
- `organizations.css` — 企業管理頁面樣式（376 行）
- `organizations.js` — 企業管理頁面邏輯（Mode B Window Bridge，326 行）
- `workflow-designer-init.js` — 主題管理 IIFE + 節點定義載入器（165 行）
- `workflow-designer.css` 新增 navbar + badge 樣式

---

## 共用靜態檔案清單

### 平台層 (`backend/app/static/`)
| 檔案 | 用途 |
|------|------|
| `css/common.css` | 跨頁面共用樣式 |
| `css/app.css` | 原有應用樣式 |
| `css/themes.css` | 主題色系 |
| `css/holidays.css` | 假日設定頁 |
| `css/schedules.css` | 班表頁 |
| `css/org-tree.css` | 部門/社群共用樣式 |
| `css/user-form.css` | 新增/編輯用戶頁 |
| `css/quick-login.css` | 開發快速登入頁 |
| `css/settings.css` | 系統設定頁 |
| `css/user-view.css` | 用戶詳情頁 |
| `css/numbering-edit.css` | 編號規則編輯頁 |
| `css/org-admins.css` | 企業管理員列表 |
| `css/organizations.css` | 企業管理頁 |
| `js/app.js` | 原有應用 JS |
| `js/auth.js` | 認證相關 JS |
| `js/holidays.js` | 假日設定頁 |
| `js/schedules.js` | 班表頁 |
| `js/groups.js` | 社群設定頁 |
| `js/user-form.js` | 新增用戶頁 |
| `js/user-edit.js` | 編輯用戶頁 |
| `js/quick-login.js` | 開發快速登入頁 |
| `js/settings.js` | 系統設定頁 |
| `js/user-view.js` | 用戶詳情頁 |
| `js/org-admins.js` | 企業管理員列表 |
| `js/organizations.js` | 企業管理頁 |

### 模組層 (`modules/form_workflow/static/modules/form_workflow/`)
| 檔案 | 用途 |
|------|------|
| `css/template-list.css` | 表單模板列表 |
| `css/workflow-list.css` | 工作流列表 |
| `css/form-designer.css` | 表單設計器 |
| `css/form-center.css` | 表單中心 |
| `css/workflow-designer.css` | 工作流設計器 |
| `css/mappings.css` | 表單流程配對列表 |
| `js/template-list.js` | 表單模板列表 |
| `js/workflow-list.js` | 工作流列表 |
| `js/form-center.js` | 表單中心 |
| `js/form-designer-main.js` | 表單設計器主邏輯 |
| `js/workflow-main.js` | 工作流設計器主邏輯 |
| `js/workflow-tree-chart.js` | 樹系圖 |
| `js/mappings.js` | 表單流程配對列表 |
| `css/category-list.css` | 分類管理 |
| `js/category-list.js` | 分類管理 |
| `js/workflow-designer-init.js` | 流程設計器初始化（主題+節點定義） |

*最後更新: 2026-02-16*
